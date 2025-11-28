# TalkPi - Voice Assistant with Ollama, Piper, and Whisper

A lightweight French voice assistant using local AI models: speech-to-text (Whisper), language understanding (Ollama), and text-to-speech (Piper). Responses stream and play sentence-by-sentence.

## Quick Start

1. **Install dependencies**: `pip install -r requirements.txt`
2. **Configure paths**: `cp .env.example .env` and edit with your local installation paths
3. **Start Ollama**: `ollama serve` (in another terminal, run `ollama pull gemma3:1b`)
4. **Run**: `python talk_to_ollama_streaming.py`

## Usage

- Press **Enter** (no text): Records ~7 seconds of audio and transcribes
- Type text + **Enter**: Sends directly to the model
- Type **'q'** + **Enter**: Exit

## Requirements

- Python 3.7+, `arecord`, `aplay` (ALSA utils)
- [Ollama](https://ollama.ai/), [whisper.cpp](https://github.com/ggerganov/whisper.cpp), [Piper](https://github.com/rhasspy/piper)

## Configuration

All paths and settings go in `.env`:

```env
OLLAMA_URL=http://127.0.0.1:11434/api/chat
OLLAMA_MODEL=gemma3:1b
PIPER_BIN=/path/to/piper
PIPER_MODEL=/path/to/model.onnx
WHISPER_BIN=/path/to/whisper-cli
WHISPER_MODEL=/path/to/model.bin
WHISPER_LANGUAGE=fr
```

## Architecture

- `record_audio()`: Captures microphone input
- `transcribe_audio()`: STT with Whisper
- `chat_stream_with_tts()`: Streams LLM response and dispatches to TTS
- `speak_chunk()`: Piper TTS synthesis
- `tts_worker()`: Background thread for audio playback

## Troubleshooting

- **"Binary not found"**: Verify paths in `.env` with `which piper` etc.
- **No audio**: Check ALSA devices with `arecord -l`
- **Ollama fails**: Ensure it's running on `http://127.0.0.1:11434`

