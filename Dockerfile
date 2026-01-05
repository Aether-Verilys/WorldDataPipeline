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
        libatk1.0-0 \
        libnss3 \
        libnspr4 \
        ffmpeg \
        tini \
        libx11-6 \
        libxext6 \
        libxrender1 \
        libxi6 \
        libxtst6 \
        libgl1-mesa-glx \
        libglu1-mesa \
        libglib2.0-0 \
        libfontconfig1 \
        libfreetype6 \
        libdbus-1-3 \
        libasound2 \
        libcups2 \
        vulkan-tools \
        libvulkan1 \
        mesa-vulkan-drivers \
    && ln -snf /usr/share/zoneinfo/${TZ} /etc/localtime \
    && echo ${TZ} > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# NVIDIA Vulkan ICD (if GPU nodes have NVIDIA drivers)
RUN mkdir -p /usr/share/vulkan/icd.d && \
    echo '{"file_format_version":"1.0.0","ICD":{"library_path":"libEGL_nvidia.so.0","api_version":"1.3.0"}}' \
    > /usr/share/vulkan/icd.d/nvidia_icd.json

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
