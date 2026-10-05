FROM python:3.13-slim

# Do not write .pyc files; print logs immediately (useful for docker logs)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5003

WORKDIR /app

# Install dependencies first so this layer is cached between code changes
COPY requirements.txt .
RUN ["pip", "install", "--no-cache-dir", "-r", "requirements.txt"]

COPY app.py .
COPY data/ ./data/

# Run as an unprivileged user instead of root
USER 10001

EXPOSE 5003

CMD ["python", "app.py"]
