#!/bin/bash
set -e

# Generate self-signed certificate for local TLS testing.
# Produces: server.key and server.crt

echo "Generating self-signed certificate for TLS..."

openssl req -x509 -newkey rsa:4096 -nodes \
  -keyout server.key \
  -out server.crt \
  -days 365 \
  -subj "/C=IN/ST=WestBengal/L=Kharagpur/O=IIT/OU=CS/CN=localhost"

echo "Certificate generated successfully"
echo "Files created: server.key, server.crt"
