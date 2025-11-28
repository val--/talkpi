#!/usr/bin/env python3
import json
import subprocess
import threading
from queue import Queue
import os
from pathlib import Path
import re

import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configuration
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
MODEL = os.getenv("OLLAMA_MODEL", "gemma3:1b")

PIPER_BIN = os.getenv("PIPER_BIN", "/usr/bin/piper")
PIPER_MODEL = os.getenv("PIPER_MODEL", "")
PIPER_CONFIG = os.getenv("PIPER_CONFIG", "")

WHISPER_BIN = os.getenv("WHISPER_BIN", "/usr/bin/whisper-cli")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "")
AUDIO_INPUT = "input.wav"

# Audio recording and processing
AUDIO_FORMAT = os.getenv("AUDIO_FORMAT", "S16_LE")
AUDIO_RATE = os.getenv("AUDIO_RATE", "16000")
AUDIO_CHANNELS = os.getenv("AUDIO_CHANNELS", "1")
DEFAULT_RECORD_DURATION = int(os.getenv("DEFAULT_RECORD_DURATION", "7"))
CHUNK_AUDIO_FILE = "chunk.wav"
TTS_TEXT_EXT_SUFFIX = ".txt"
SENTENCE_SEPARATORS = [".", "!", "?", ":"]
MARKDOWN_CHARS = ["*", "_", "`", "#"]
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "en")

MD_LINK_RE = re.compile(r'\[([^\]]+)\]\([^)]+\)')

def clean_for_tts(text: str) -> str:
    """Clean text for TTS: remove markdown links, formatting chars, and normalize spaces."""
    if not text:
        return text

    text = MD_LINK_RE.sub(r'\1', text)
    for ch in MARKDOWN_CHARS:
        text = text.replace(ch, "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def speak_chunk(text: str):
    """Use Piper to read a text chunk."""
    if not text.strip():
        return

    p = subprocess.Popen(
        [
            PIPER_BIN,
            "-m", PIPER_MODEL,
            "-c", PIPER_CONFIG,
            "-f", CHUNK_AUDIO_FILE,
        ],
        stdin=subprocess.PIPE,
        text=True,
        stderr=subprocess.DEVNULL,
    )
    p.communicate(text)
    p.wait()

    subprocess.run(["aplay", CHUNK_AUDIO_FILE], stderr=subprocess.DEVNULL)


def tts_worker(queue: Queue):
    """Worker thread that processes text chunks for speech synthesis."""
    while True:
        item = queue.get()
        if item is None:
            queue.task_done()
            break
        try:
            speak_chunk(item)
        finally:
            queue.task_done()


# ======== STT : recording and transcription ========

def record_audio(path: str = AUDIO_INPUT, duration: int = DEFAULT_RECORD_DURATION):
    """Record audio from microphone for the specified duration."""
    print(f"\n[Enregistrement] Parle maintenant ({duration} secondes)...")
    cmd = [
        "arecord",
        "-f", AUDIO_FORMAT,
        "-r", AUDIO_RATE,
        "-c", AUDIO_CHANNELS,
        "-d", str(duration),
        path,
    ]

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print("Erreur pendant l'enregistrement :", e)
        return None

    print("[Enregistrement terminé]")
    return path


def transcribe_audio(path: str = AUDIO_INPUT) -> str:
    """Transcribe audio file to text using whisper.cpp."""
    print("[Transcription] En cours avec whisper.cpp...")

    if not os.path.exists(WHISPER_BIN):
        print(f"Erreur: binaire whisper.cpp introuvable: {WHISPER_BIN}")
        return ""

    if not os.path.exists(WHISPER_MODEL):
        print(f"Erreur: modèle Whisper introuvable: {WHISPER_MODEL}")
        return ""

    if not os.path.exists(path):
        print(f"Fichier audio introuvable: {path}")
        return ""

    cmd = [
        WHISPER_BIN,
        "-m", WHISPER_MODEL,
        "-f", path,
        "-otxt",
        "-l", WHISPER_LANGUAGE,
    ]

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print("Erreur pendant la transcription :", e)
        return ""

    txt_path = Path(path + TTS_TEXT_EXT_SUFFIX)
    if not txt_path.exists():
        print("Fichier texte de transcription introuvable :", txt_path)
        return ""

    text = txt_path.read_text(encoding="utf-8").strip()
    print(f"[Transcription] \"{text}\"")
    return text


# ======== Ollama streaming + dispatch vers TTS ========

def chat_stream_with_tts(prompt: str, history):
    """Stream Ollama response while sending sentences to Piper for TTS."""
    messages = history + [
        {"role": "user", "content": prompt},
    ]

    payload = {
        "model": MODEL,
        "stream": True,
        "messages": messages,
    }

    q = Queue()
    t = threading.Thread(target=tts_worker, args=(q,), daemon=True)
    t.start()

    full_text = ""
    current_sentence = ""

    print(">>> Question :", prompt)
    print("\n<<< Réponse d'Ollama (streaming) :\n")

    with requests.post(OLLAMA_URL, json=payload, stream=True) as resp:
        resp.raise_for_status()

        for line in resp.iter_lines():
            if not line:
                continue

            try:
                data = json.loads(line.decode("utf-8"))
            except json.JSONDecodeError:
                continue

            message = data.get("message", {})
            chunk = message.get("content", "")
            if not chunk:
                continue

            print(chunk, end="", flush=True)

            full_text += chunk
            current_sentence += chunk

            if any(sep in current_sentence for sep in SENTENCE_SEPARATORS):
                sentence_to_speak = current_sentence.strip()
                if sentence_to_speak:
                    q.put(clean_for_tts(sentence_to_speak))
                current_sentence = ""

        if current_sentence.strip():
            q.put(clean_for_tts(current_sentence.strip()))

    print("\n\n[Fin de la réponse]\n")

    q.put(None)
    q.join()

    return full_text


# ======== Main loop: voice assistant ========

def main():
    system_prompt = (
        "Tu es un assistant vocal qui répond en français de manière claire "
        "et pédagogique en quelques phrases. "
        "IMPORTANT : réponds en texte brut, sans Markdown, sans gras, sans italique, "
        "sans listes à puces, sans titres, sans emojis."
    )
    history = [{"role": "system", "content": system_prompt}]

    print("=== Assistant vocal Ollama + Piper + Whisper ===")
    print("Appuie sur Entrée pour parler au micro.")
    print("Ou tape une question au clavier, puis Entrée.")
    print("Tape 'q' puis Entrée pour quitter.\n")

    while True:
        try:
            user_input = input(">> ")
        except (EOFError, KeyboardInterrupt):
            print("\nAu revoir !")
            break

        if user_input.lower().startswith("q"):
            print("Au revoir !")
            break

        if user_input.strip():
            prompt = user_input.strip()
        else:
            wav_path = record_audio(duration=DEFAULT_RECORD_DURATION)
            if not wav_path:
                continue

            prompt = transcribe_audio(wav_path)
            if not prompt:
                print("Je n'ai rien compris, réessaie.")
                continue

        answer = chat_stream_with_tts(prompt, history)
        history.append({"role": "user", "content": prompt})
        history.append({"role": "assistant", "content": answer})


if __name__ == "__main__":
    main()
