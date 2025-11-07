# Base Python image
FROM python:3.11-slim

# Environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DEFAULT_TIMEOUT=120

# 使用国内 APT / PyPI 镜像以加速构建（适配 Debian 基础镜像，如 trixie/bookworm）
# 如需更换为阿里或中科大镜像，可替换下方 URL。
RUN sed -i -e 's|http://deb.debian.org/debian|https://mirrors.tuna.tsinghua.edu.cn/debian|g' \
           -e 's|http://security.debian.org/debian-security|https://mirrors.tuna.tsinghua.edu.cn/debian-security|g' /etc/apt/sources.list

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
