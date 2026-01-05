# syntax=docker/dockerfile:1

FROM python:3.11-slim

# Prevent Python from writing pyc files and enable unbuffered logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps
# - psutil may need build tools on some platforms
# - ffmpeg-python needs the ffmpeg binary
# - tini helps with proper signal handling in k8s
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        ffmpeg \
        tini \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

EXPOSE 5000

ENTRYPOINT ["tini", "--", "python", "app.py"]
CMD ["--help"]
