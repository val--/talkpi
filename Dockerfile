FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install Piper TTS
RUN mkdir -p /opt/piper && \
    wget -q https://github.com/rhasspy/piper/releases/download/v1.2.0/piper_amd64.tar.gz -O /tmp/piper.tar.gz && \
    tar -xzf /tmp/piper.tar.gz -C /opt/piper --strip-components=1 && \
    rm /tmp/piper.tar.gz && \
    chmod +x /opt/piper/piper

# Download a default Piper voice model (French)
RUN mkdir -p /opt/piper/models && \
    wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx -O /opt/piper/models/fr_FR-siwis-medium.onnx && \
    wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx.json -O /opt/piper/models/fr_FR-siwis-medium.onnx.json

# Install whisper.cpp (whisper-cli) with all shared libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    && git clone https://github.com/ggerganov/whisper.cpp.git /tmp/whisper.cpp \
    && cd /tmp/whisper.cpp \
    && cmake -B build -DBUILD_SHARED_LIBS=ON \
    && cmake --build build --config Release -j$(nproc) \
    && cp build/bin/whisper-cli /usr/local/bin/whisper-cli \
    && find build -name "*.so*" -exec cp {} /usr/local/lib/ \; \
    && chmod +x /usr/local/bin/whisper-cli \
    && ldconfig \
    && rm -rf /tmp/whisper.cpp \
    && apt-get remove -y build-essential cmake git \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Download whisper model (tiny for speed, or base for better quality)
RUN mkdir -p /opt/whisper/models && \
    wget -q https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin -O /opt/whisper/models/ggml-tiny.bin

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set environment variables
ENV PIPER_BIN=/opt/piper/piper
ENV PIPER_MODEL=/opt/piper/models/fr_FR-siwis-medium.onnx
ENV PIPER_CONFIG=/opt/piper/models/fr_FR-siwis-medium.onnx.json
ENV WHISPER_BIN=/usr/local/bin/whisper-cli
ENV WHISPER_MODEL=/opt/whisper/models/ggml-tiny.bin
ENV WHISPER_LANGUAGE=fr
ENV OLLAMA_URL=http://ollama:11434/api/chat
ENV OLLAMA_MODEL=gemma3:1b

EXPOSE 5000

CMD ["python", "server.py"]

