FROM registry.baidubce.com/cce-ai-native/pytorch:22.08-py3

# Prevent Python from writing pyc files and enable unbuffered logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Avoid interactive tzdata prompts during build
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Shanghai

WORKDIR /app

# System deps (no interactive prompts)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        tzdata \
        libnss3 \
        libnspr4 \
        ffmpeg \
        tini \
    && ln -snf /usr/share/zoneinfo/${TZ} /etc/localtime \
    && echo ${TZ} > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# Python 3.11 (avoid Ubuntu PPA/network issues by using conda in base image)
# NVIDIA pytorch images typically ship conda at /opt/conda.
RUN test -x /opt/conda/bin/conda

RUN /opt/conda/bin/conda create -y -n py311 python=3.11 pip \
    && /opt/conda/bin/conda clean -afy

ENV PATH=/opt/conda/envs/py311/bin:$PATH

# Install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir -U pip \
    && python -m pip install --no-cache-dir -r /app/requirements.txt

# Copy project code
COPY . /app

EXPOSE 5000

ENTRYPOINT ["tini", "--", "python", "app.py"]
CMD ["--help"]
