FROM python:3.9-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY server.py .
COPY server.crt server.key ./

# Expose port
EXPOSE 9999

# Run server
CMD ["python", "server.py"]
