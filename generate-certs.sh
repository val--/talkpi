#!/bin/bash
# Generate self-signed SSL certificates for HTTPS

CERT_DIR="${1:-./certs}"
mkdir -p "$CERT_DIR"

# Generate private key and self-signed certificate
openssl req -x509 -newkey rsa:4096 \
    -keyout "$CERT_DIR/key.pem" \
    -out "$CERT_DIR/cert.pem" \
    -days 365 \
    -nodes \
    -subj "/CN=talkpi/O=TalkPi/C=FR" \
    -addext "subjectAltName=DNS:localhost,IP:127.0.0.1,IP:192.168.1.212"

echo "✅ Certificates generated in $CERT_DIR/"
echo "   - cert.pem (certificate)"
echo "   - key.pem (private key)"
echo ""
echo "⚠️  Note: Self-signed certificates will show a browser warning."
echo "   Click 'Advanced' → 'Proceed to site' to continue."


