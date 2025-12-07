# TalkPi - Voice Assistant with Ollama, Piper, and Whisper

A lightweight French voice assistant using local AI models: speech-to-text (Whisper), language understanding (Ollama), and text-to-speech (Piper). Responses stream and play sentence-by-sentence.

![Michk.IA Preview](preview.png)

## Features

- 🎤 **Voice input** via browser microphone (requires HTTPS)
- 🔊 **Text-to-speech** with Piper (streams sentence by sentence)
- 🧠 **Local LLM** via Ollama (llama3.1, gemma3, etc.)
- 🎯 **100% local** - no cloud dependencies
- 🐳 **Docker support** for easy deployment

## Architecture Options

### Option 1: Everything on one powerful server (Recommended)

All processing happens on a single server. Clients only need a web browser.

```
┌─────────────┐      ┌───────────────────────────────────────────────┐
│   Browser   │ ──── │           Server (e.g. 192.168.1.212)         │
│ (any device)│      │  ┌─────────┐  ┌─────────┐  ┌───────────────┐  │
│             │ HTTPS│  │ TalkPi  │──│ Whisper │──│ Ollama + LLM  │  │
│             │      │  │ (Flask) │  │  (STT)  │  │ (llama3.1)    │  │
│             │      │  └─────────┘  └─────────┘  └───────────────┘  │
│             │      │       │                                       │
│             │      │  ┌─────────┐                                  │
│             │      │  │  Piper  │                                  │
│             │      │  │  (TTS)  │                                  │
│             │      │  └─────────┘                                  │
└─────────────┘      └───────────────────────────────────────────────┘
```

### Option 2: Distributed setup

TalkPi on one machine, Ollama on another.

```
┌─────────────┐      ┌──────────────────────┐      ┌─────────────────┐
│   Browser   │ ──── │  TalkPi Server       │ ──── │ Ollama Server   │
│             │      │  - Whisper (STT)     │      │ - LLM           │
│             │      │  - Piper (TTS)       │      │                 │
└─────────────┘      └──────────────────────┘      └─────────────────┘
```

---

## Quick Start: Server Deployment (Docker)

Deploy everything on a powerful server with GPU/good CPU:

### 1. Clone the repository

```bash
git clone https://github.com/val--/talkpi.git
cd talkpi
```

### 2. Create configuration file

```bash
cat > env.server << 'EOF'
# Ollama Configuration (adjust URL if Ollama is on another machine)
OLLAMA_URL=http://host.docker.internal:11434/api/chat
OLLAMA_MODEL=llama3.1:latest

# HTTPS Configuration (required for microphone access)
USE_HTTPS=true
PORT=5000
SSL_CERT=/app/certs/cert.pem
SSL_KEY=/app/certs/key.pem

# System Prompt (Persona)
SYSTEM_PROMPT=Tu es Michk.IA, un assistant IA incarné par un chat blanc aux yeux verts. Tu es intelligent, curieux et un peu mystérieux. Tu réponds de manière concise mais utile. Tu peux être espiègle parfois, comme un vrai chat. Tu parles français.

# Piper TTS
PIPER_BIN=/opt/piper/piper
PIPER_MODEL=/opt/piper/models/fr_FR-siwis-medium.onnx
PIPER_CONFIG=/opt/piper/models/fr_FR-siwis-medium.onnx.json

# Whisper STT
WHISPER_BIN=/usr/local/bin/whisper-cli
WHISPER_MODEL=/opt/whisper/models/ggml-tiny.bin
WHISPER_LANGUAGE=fr

# Audio
AUDIO_FORMAT=S16_LE
AUDIO_RATE=16000
AUDIO_CHANNELS=1
DEFAULT_RECORD_DURATION=6
EOF
```

### 3. Make sure Ollama is running

```bash
# If Ollama is on the same machine
ollama serve &
ollama pull llama3.1:latest
```

### 4. Build and run with Docker

```bash
docker compose -f docker-compose.server.yml up -d --build
```

### 5. Access from any browser

```
https://YOUR_SERVER_IP:5001
```

⚠️ **First access**: You'll see a certificate warning (self-signed cert). Click **"Advanced"** → **"Proceed"** to continue.

---

## Quick Start: Local Development

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure paths

```bash
cp env.server .env
# Edit .env with your local paths
```

### 3. Start Ollama

```bash
ollama serve
ollama pull llama3.1:latest
```

### 4. Run the server

```bash
python server.py
```

### 5. Open in browser

- HTTP (no mic): `http://localhost:5000`
- HTTPS (with mic): Generate certs first with `./generate-certs.sh`, set `USE_HTTPS=true`

---

## Remote Ollama Configuration

If your Ollama instance runs on a different machine:

```env
# In env.server or .env
OLLAMA_URL=http://192.168.1.212:11434/api/chat
OLLAMA_MODEL=llama3.1:latest
```

Make sure Ollama is configured to accept remote connections:

```bash
# On the Ollama server, set this before starting:
OLLAMA_HOST=0.0.0.0 ollama serve
```

Or add to systemd service (`/etc/systemd/system/ollama.service`):
```ini
Environment="OLLAMA_HOST=0.0.0.0"
```

---

## HTTPS & Microphone Access

Modern browsers require **HTTPS** for microphone access (except localhost). TalkPi includes:

- **Self-signed certificates** generated automatically in Docker
- **Manual generation**: `./generate-certs.sh`

### Browser Certificate Warning

First time accessing the app, you'll see a security warning. This is normal for self-signed certificates:

1. Click **"Advanced"** or **"Show Details"**
2. Click **"Proceed to [IP]"** or **"Accept the Risk"**

### Alternative: Chrome Flag (Development only)

```bash
google-chrome --unsafely-treat-insecure-origin-as-secure="http://192.168.1.212:5001"
```

---

## Usage

| Action | Description |
|--------|-------------|
| **Type + Enter** | Send text message to AI |
| **Click "Parler"** | Record voice (7 seconds) |
| **Click during recording** | Stop early |
| **"Effacer"** | Clear conversation |
| **"Historique"** | Load server-side history |

---

## Configuration Reference

| Variable | Description | Default |
|----------|-------------|---------|
| `OLLAMA_URL` | Ollama API endpoint | `http://127.0.0.1:11434/api/chat` |
| `OLLAMA_MODEL` | Model to use | `gemma3:1b` |
| `USE_HTTPS` | Enable HTTPS | `false` |
| `PORT` | Server port | `5000` |
| `SSL_CERT` | Path to SSL certificate | `/app/certs/cert.pem` |
| `SSL_KEY` | Path to SSL private key | `/app/certs/key.pem` |
| `SYSTEM_PROMPT` | AI persona/instructions | Michk.IA prompt |
| `PIPER_BIN` | Piper TTS binary | `/opt/piper/piper` |
| `PIPER_MODEL` | Piper voice model | French siwis-medium |
| `WHISPER_BIN` | Whisper binary | `/usr/local/bin/whisper-cli` |
| `WHISPER_MODEL` | Whisper model file | `ggml-tiny.bin` |
| `WHISPER_LANGUAGE` | Transcription language | `fr` |

---

## Docker Files

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Basic setup (includes local Ollama) |
| `docker-compose.server.yml` | Server deployment (external Ollama) |
| `env.docker` | Config for docker-compose.yml |
| `env.server` | Config for server deployment |

---

## Troubleshooting

### "Enregistrement non pris en charge"
- Use **HTTPS** (`https://...`) not HTTP
- Or launch Chrome with the `--unsafely-treat-insecure-origin-as-secure` flag

### Connection refused
```bash
# Check if port is open (5001 for server deployment, 5000 for local)
sudo ufw allow 5001/tcp

# Check Docker is exposing the port
docker ps
```

### Ollama not reachable
```bash
# Test Ollama directly
curl http://YOUR_OLLAMA_IP:11434/api/tags

# Make sure Ollama accepts remote connections
OLLAMA_HOST=0.0.0.0 ollama serve
```

### No audio playback
- Check browser allows autoplay
- Check console for audio errors (F12 → Console)

### Docker permission denied
```bash
# Add user to docker group
sudo usermod -aG docker $USER
# Log out and back in, or:
newgrp docker
```

---

## Requirements

- **Server**: Docker, or Python 3.10+ with ffmpeg
- **Client**: Modern browser (Chrome, Firefox, Edge)
- **Ollama**: Running instance with a model pulled

---

## License

MIT
