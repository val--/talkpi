#!/usr/bin/env python3
from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS
import sys
import base64
import json
import requests
import subprocess
import tempfile
import os
import shutil
import wave

# Import existing functions and configuration
from talk_to_ollama_streaming import (
    chat_stream_with_tts,
    transcribe_audio,
    clean_for_tts,
    PIPER_BIN,
    PIPER_MODEL,
    PIPER_CONFIG,
    CHUNK_AUDIO_FILE,
    MODEL,
    OLLAMA_URL,
    SENTENCE_SEPARATORS,
)
import threading

app = Flask(__name__, static_folder='front', static_url_path='')
CORS(app)

# ============================================
# CONFIGURATION - System Prompt (Persona)
# ============================================
SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", """Tu es Michk.IA, un assistant IA incarné par un chat blanc aux yeux verts.
Tu es intelligent, curieux et un peu mystérieux. Tu réponds de manière concise mais utile.
Tu peux être espiègle parfois, comme un vrai chat. Tu parles français.""")
# ============================================

# In-memory conversation history (persist during server runtime)
# Start with the system prompt
conversation_history = [{"role": "system", "content": SYSTEM_PROMPT}]
history_lock = threading.Lock()


@app.route('/')
def index():
    # Serve the frontend index
    return app.send_static_file('index.html')


@app.route('/<path:path>')
def static_proxy(path):
    # Serve other static files (css/js) from the front folder
    return send_from_directory(app.static_folder, path)


def synthesize_to_wav(text: str) -> bytes:
    """Synthesize text to wav using Piper and return raw bytes."""
    # Clean text for TTS (remove markdown, emojis, etc.)
    text_to_speak = clean_for_tts(text)

    # Call Piper to generate the wav file
    p = subprocess.Popen(
        [
            PIPER_BIN,
            "-m", PIPER_MODEL,
            "-c", PIPER_CONFIG,
            "-f", CHUNK_AUDIO_FILE,
        ],
        stdin=subprocess.PIPE,
        text=True,
    )
    p.communicate(text_to_speak)
    p.wait()

    if not os.path.exists(CHUNK_AUDIO_FILE):
        return b""

    try:
        with open(CHUNK_AUDIO_FILE, "rb") as fh:
            data = fh.read()
    except Exception:
        return b""

    return data


def convert_to_wav(input_path: str) -> str:
    """Convert input audio file to WAV using ffmpeg if necessary.

    Returns path to a WAV file (may be the original if already WAV).
    Raises RuntimeError if conversion fails or ffmpeg is not available.
    """
    # If input already endswith .wav, return it
    if input_path.lower().endswith('.wav'):
        return input_path

    ffmpeg_path = shutil.which('ffmpeg')
    if not ffmpeg_path:
        # No ffmpeg available; try returning original path (may fail downstream)
        raise RuntimeError('ffmpeg not found; cannot convert audio to WAV')

    wav_fd = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    wav_path = wav_fd.name
    wav_fd.close()

    # Convert to 16-bit PCM WAV which whisper.cpp expects
    cmd = [
        ffmpeg_path, '-y', '-i', input_path,
        '-ar', '16000',
        '-ac', '1',
        '-c:a', 'pcm_s16le',
        wav_path,
    ]
    try:
        proc = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode('utf-8', errors='replace') if e.stderr else ''
        try:
            os.unlink(wav_path)
        except Exception:
            pass
        raise RuntimeError(f'ffmpeg conversion failed: {stderr}') from e

    return wav_path


@app.route('/api/test-stream', methods=['GET'])
def test_stream():
    """Test endpoint to verify SSE works at all"""
    def gen():
        for i in range(5):
            ev = f"event: message\ndata: {json.dumps({'msg': f'test {i}', 'time': i})}\n\n"
            print(f'TEST: yielding event {i}')
            yield ev
        print('TEST: stream done')
    headers = {'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    return Response(gen(), mimetype='text/event-stream', headers=headers)


@app.route('/api/test-audio-stream', methods=['GET'])
def test_audio_stream():
    """Test endpoint to verify audio streaming works"""
    def gen():
        test_sentences = [
            "Bonjour, c'est un test.",
            "Voici le deuxième message.",
            "Et voici le troisième.",
        ]
        for i, sentence in enumerate(test_sentences):
            print(f'TEST_AUDIO: synthesizing: {sentence}')
            audio_bytes = synthesize_to_wav(sentence)
            audio_b64 = base64.b64encode(audio_bytes).decode('ascii') if audio_bytes else None
            print(f'TEST_AUDIO: synthesized {len(audio_bytes)} bytes')
            ev = f"event: audio\ndata: {json.dumps({'audio_base64': audio_b64, 'sentence': sentence})}\n\n"
            print(f'TEST_AUDIO: yielding audio event {i}')
            yield ev
        print('TEST_AUDIO: stream done')
    headers = {'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    return Response(gen(), mimetype='text/event-stream', headers=headers)


@app.route('/api/chat-text', methods=["POST"])
def chat_text():
    data = request.get_json(force=True)
    prompt = data.get("text", "")
    if not prompt:
        return jsonify({"error": "empty prompt"}), 400

    # Use server-side history and persist the new turn
    full_text = chat_stream_with_tts(prompt, history=[], play_tts=False)

    # store in server-side history
    with history_lock:
        conversation_history.append({"role": "user", "content": prompt})
        conversation_history.append({"role": "assistant", "content": full_text})

    audio_bytes = synthesize_to_wav(full_text)
    audio_b64 = base64.b64encode(audio_bytes).decode("ascii") if audio_bytes else None
    audio_len = len(audio_bytes) if audio_bytes else 0

    return jsonify({
        "text": full_text,
        "audio_base64": audio_b64,
        "audio_available": bool(audio_b64),
        "audio_len": audio_len,
    })


def _stream_ollama_response(messages):
    """Internal helper: stream Ollama response given messages list and yield dict items.
    
    Strategy: yield text chunks immediately, then when a sentence boundary is hit,
    synthesize audio (blocking but acceptable) and yield audio event.
    This ensures audio events arrive interleaved with text chunks.
    """
    payload = {
        "model": MODEL,
        "stream": True,
        "messages": messages,
    }
    state = {'full_text': '', 'current_sentence': ''}
    
    with requests.post(OLLAMA_URL, json=payload, stream=True) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            try:
                data = json.loads(line.decode("utf-8"))
            except Exception:
                continue
            message = data.get("message", {})
            chunk = message.get("content", "")
            if not chunk:
                continue

            state['full_text'] += chunk
            state['current_sentence'] += chunk

            # yield the textual chunk immediately
            yield {'chunk': chunk, 'state': state}

            # if current_sentence contains a sentence separator, synthesize and yield audio
            if any(sep in state['current_sentence'] for sep in SENTENCE_SEPARATORS):
                sentence_to_speak = state['current_sentence'].strip()
                if sentence_to_speak:
                    cleaned = clean_for_tts(sentence_to_speak)
                    if cleaned.strip():
                        print(f'[SYNTH] synthesizing: {cleaned[:60]}...')
                        audio_bytes = synthesize_to_wav(sentence_to_speak)
                        audio_b64 = base64.b64encode(audio_bytes).decode('ascii') if audio_bytes else None
                        print(f'[SYNTH] synthesized {len(audio_bytes)} bytes, yielding audio event')
                        yield {'audio_base64': audio_b64, 'sentence': sentence_to_speak, 'state': state}
                state['current_sentence'] = ""

        # after stream ends, if there's remaining text, synthesize and yield
        if state['current_sentence'].strip():
            cleaned = clean_for_tts(state['current_sentence'].strip())
            if cleaned.strip():
                print(f'[SYNTH] synthesizing final: {cleaned[:60]}...')
                audio_bytes = synthesize_to_wav(state['current_sentence'].strip())
                audio_b64 = base64.b64encode(audio_bytes).decode('ascii') if audio_bytes else None
                print(f'[SYNTH] synthesized {len(audio_bytes)} bytes, yielding final audio event')
                yield {'audio_base64': audio_b64, 'sentence': state['current_sentence'].strip(), 'state': state}


from flask import Response


@app.route('/api/chat-text-stream', methods=['POST'])
def chat_text_stream():
    data = request.get_json(force=True)
    prompt = data.get('text', '')
    if not prompt:
        return jsonify({"error": "empty prompt"}), 400

    messages = []
    final_state = None
    
    # stream generator: emits SSE formatted events
    def gen():
        nonlocal final_state
        try:
            # stream partial chunks and audio; capture final_state
            for item in _stream_ollama_response(messages + [{"role": "user", "content": prompt}]):
                final_state = item.get('state')  # keep updating state reference
                
                if 'chunk' in item:
                    ev = f"event: partial\n"
                    ev += f"data: {json.dumps({'chunk': item['chunk']})}\n\n"
                    print('STREAM: yielding partial chunk len=', len(item['chunk']))
                    yield ev
                if 'audio_base64' in item:
                    ev = f"event: audio\n"
                    ev += f"data: {json.dumps({'audio_base64': item.get('audio_base64'), 'sentence': item.get('sentence')})}\n\n"
                    print(f'[SSE_YIELD] sending audio event, b64_len={len(item.get("audio_base64", ""))}')
                    yield ev

            # Use captured full_text from streaming (avoid re-calling Ollama)
            full_text = final_state['full_text'] if final_state else ""

            # persist history
            with history_lock:
                conversation_history.append({"role": "user", "content": prompt})
                conversation_history.append({"role": "assistant", "content": full_text})

            # final event with no additional audio (already sent per-sentence)
            ev = f"event: final\n"
            ev += f"data: {json.dumps({'text': full_text, 'audio_base64': None})}\n\n"
            yield ev
        except Exception as e:
            err = str(e)
            ev = f"event: error\n"
            ev += f"data: {json.dumps({'error': err})}\n\n"
            yield ev

    # disable buffering in proxies (nginx) with X-Accel-Buffering and no-cache
    headers = {'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    return Response(gen(), mimetype='text/event-stream', headers=headers)


@app.route('/api/chat-audio-stream', methods=['POST'])
def chat_audio_stream():
    # Accept audio file uploaded by browser (optional)
    if 'file' not in request.files:
        return jsonify({"error": "no file uploaded"}), 400

    f = request.files['file']
    if f.filename == '':
        return jsonify({"error": "empty filename"}), 400

    # save uploaded file to a temporary file preserving original extension
    orig_ext = os.path.splitext(f.filename)[1] or ''
    with tempfile.NamedTemporaryFile(suffix=orig_ext, delete=False) as tmp:
        tmp.write(f.read())
        tmp_path = tmp.name

    def gen():
        wav_path = None
        final_state = None
        try:
            try:
                wav_path = convert_to_wav(tmp_path)
            except RuntimeError as e:
                wav_path = tmp_path
                ffmpeg_conv_msg = str(e)
            # Do transcription first and send it immediately
            transcript = transcribe_audio(wav_path)
            if not transcript:
                ev = f"event: error\n"
                ev += f"data: {json.dumps({'error': 'transcription failed'})}\n\n"
                yield ev
                return

            # send transcript event
            ev = f"event: transcript\n"
            ev += f"data: {json.dumps({'transcript': transcript})}\n\n"
            yield ev

            # now stream the LLM response and audio chunks per sentence; capture final state
            for item in _stream_ollama_response([{"role": "user", "content": transcript}]):
                final_state = item.get('state')  # keep updating state reference
                
                if 'chunk' in item:
                    ev = f"event: partial\n"
                    ev += f"data: {json.dumps({'chunk': item['chunk']})}\n\n"
                    yield ev
                if 'audio_base64' in item:
                    ev = f"event: audio\n"
                    ev += f"data: {json.dumps({'audio_base64': item.get('audio_base64'), 'sentence': item.get('sentence')})}\n\n"
                    yield ev

            # Use captured full_text from streaming (avoid re-calling Ollama)
            full_text = final_state['full_text'] if final_state else ""
            
            # persist history
            with history_lock:
                conversation_history.append({"role": "user", "content": transcript})
                conversation_history.append({"role": "assistant", "content": full_text})

            # final event with no additional audio (already sent per-sentence)
            ev = f"event: final\n"
            ev += f"data: {json.dumps({'text': full_text, 'audio_base64': None})}\n\n"
            yield ev

        except Exception as e:
            ev = f"event: error\n"
            ev += f"data: {json.dumps({'error': str(e)})}\n\n"
            yield ev
        finally:
            try:
                if wav_path and wav_path != tmp_path:
                    os.unlink(wav_path)
            except Exception:
                pass
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    headers = {'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    return Response(gen(), mimetype='text/event-stream', headers=headers)


@app.route("/api/chat-audio", methods=["POST"])
def chat_audio():
    # Accept audio file uploaded by browser (optional)
    if "file" not in request.files:
        return jsonify({"error": "no file uploaded"}), 400

    f = request.files["file"]
    if f.filename == "":
        return jsonify({"error": "empty filename"}), 400

    # save uploaded file to a temporary file preserving original extension
    orig_ext = os.path.splitext(f.filename)[1] or ''
    with tempfile.NamedTemporaryFile(suffix=orig_ext, delete=False) as tmp:
        tmp.write(f.read())
        tmp_path = tmp.name

    try:
        # Convert uploaded file to WAV if needed
        wav_path = None
        ffmpeg_conv_msg = None
        try:
            try:
                wav_path = convert_to_wav(tmp_path)
            except RuntimeError as e:
                # conversion failed or ffmpeg not found; try using original file
                wav_path = tmp_path
                ffmpeg_conv_msg = str(e)

            # Diagnostics for the wav file before transcription
            diag = {
                'wav_path': wav_path,
                'exists': os.path.exists(wav_path),
                'size': os.path.getsize(wav_path) if os.path.exists(wav_path) else 0,
                'wave_read_error': None,
                'ffmpeg_error': ffmpeg_conv_msg,
            }
            try:
                with wave.open(wav_path, 'rb') as wf:
                    params = wf.getparams()
                    diag['wave_params'] = {
                        'nchannels': params.nchannels,
                        'sampwidth': params.sampwidth,
                        'framerate': params.framerate,
                        'nframes': params.nframes,
                        'comptype': params.comptype,
                        'compname': params.compname,
                    }
            except Exception as e:
                diag['wave_read_error'] = str(e)

            transcript = transcribe_audio(wav_path)
            if not transcript:
                print('Transcription failed; diagnostics:', diag)
                return jsonify({"error": "transcription failed", "diagnostics": diag}), 500

            # Disable server-side TTS playback (play_tts=False)
            full_text = chat_stream_with_tts(transcript, history=[], play_tts=False)

            # persist history
            with history_lock:
                conversation_history.append({"role": "user", "content": transcript})
                conversation_history.append({"role": "assistant", "content": full_text})

            audio_bytes = synthesize_to_wav(full_text)
            audio_b64 = base64.b64encode(audio_bytes).decode("ascii") if audio_bytes else None
            audio_len = len(audio_bytes) if audio_bytes else 0

            return jsonify({
                "transcript": transcript,
                "text": full_text,
                "audio_base64": audio_b64,
                "audio_available": bool(audio_b64),
                "audio_len": audio_len,
            })
        finally:
            # cleanup converted wav if it was created and is different from tmp_path
            if wav_path and wav_path != tmp_path:
                try:
                    os.unlink(wav_path)
                except Exception:
                    pass
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


@app.route('/api/history', methods=['GET'])
def get_history():
    with history_lock:
        return jsonify(list(conversation_history))


@app.route('/api/clear-history', methods=['POST'])
def clear_history():
    global conversation_history
    with history_lock:
        # Keep the system prompt when clearing
        conversation_history = [{"role": "system", "content": SYSTEM_PROMPT}]
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    import ssl
    
    # Check for SSL certificates
    cert_file = os.getenv("SSL_CERT", "/app/certs/cert.pem")
    key_file = os.getenv("SSL_KEY", "/app/certs/key.pem")
    use_https = os.getenv("USE_HTTPS", "false").lower() == "true"
    port = int(os.getenv("PORT", "5000"))
    
    if use_https and os.path.exists(cert_file) and os.path.exists(key_file):
        print(f"🔒 Starting HTTPS server on port {port}")
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(cert_file, key_file)
        app.run(host="0.0.0.0", port=port, debug=False, ssl_context=ssl_context)
    else:
        print(f"🔓 Starting HTTP server on port {port}")
        app.run(host="0.0.0.0", port=port, debug=False)

