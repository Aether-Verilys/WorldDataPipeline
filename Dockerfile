# syntax=docker/dockerfile:1

FROM registry.baidubce.com/cce-ai-native/pytorch:22.08-py3

# Prevent Python from writing pyc files and enable unbuffered logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install Python 3.11
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        software-properties-common \
        curl \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        python3.11 \
        python3.11-dev \
        python3.11-distutils \
        build-essential \
        ca-certificates \
        ffmpeg \
        tini \
    && curl -sS https://bootstrap.pypa.io/get-pip.py | python3.11 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN python3.11 -m pip install --no-cache-dir -U pip \
    && python3.11 -m pip install --no-cache-dir -r /app/requirements.txt

# Copy project code
COPY . /app

EXPOSE 5000

ENTRYPOINT ["tini", "--", "python3.11", "app.py"]
CMD ["--help"]
