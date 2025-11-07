# Base Python image
FROM python:3.11-slim

# Environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    DEBIAN_FRONTEND=noninteractive

# 使用国内 APT / PyPI 镜像以加速构建（Debian 12/13 通用）
# 直接写入 /etc/apt/sources.list，并移除 debian.sources，避免复杂的 sed 转义问题
RUN set -eux; \
    . /etc/os-release; CODENAME="${VERSION_CODENAME:-stable}"; \
    rm -f /etc/apt/sources.list.d/debian.sources; \
    printf "deb https://mirrors.tuna.tsinghua.edu.cn/debian %s main contrib non-free non-free-firmware\n" "$CODENAME" > /etc/apt/sources.list; \
    printf "deb https://mirrors.tuna.tsinghua.edu.cn/debian %s-updates main contrib non-free non-free-firmware\n" "$CODENAME" >> /etc/apt/sources.list; \
    printf "deb https://mirrors.tuna.tsinghua.edu.cn/debian-security %s-security main contrib non-free non-free-firmware\n" "$CODENAME" >> /etc/apt/sources.list; \
    echo 'Acquire::Retries "5"; Acquire::http::Pipeline-Depth "0"; Acquire::http::No-Cache "true";' > /etc/apt/apt.conf.d/99retries

# 允许通过构建参量覆盖 PyPI 源：--build-arg PIP_INDEX_URL=...
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV PIP_INDEX_URL=${PIP_INDEX_URL}

WORKDIR /app

# System deps for psycopg2 and building wheels
RUN apt-get -o Acquire::Retries=5 -o Acquire::http::Pipeline-Depth=0 update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Project files
COPY . .

# Ensure scripts executable and set default port
RUN chmod +x start.sh
EXPOSE 8000

# Start
CMD ["bash", "start.sh"]
