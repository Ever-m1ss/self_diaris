# Base Python image
FROM python:3.11-slim

# Environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    DEBIAN_FRONTEND=noninteractive

# 使用国内 APT / PyPI 镜像以加速构建（适配 Debian 12/13，采用 debian.sources 的新格式）
# 优先替换 /etc/apt/sources.list.d/debian.sources；若不存在则回退到 /etc/apt/sources.list
RUN set -eux; \
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i -E 's|deb\\.debian\\.org|mirrors.tuna.tsinghua.edu.cn|g; s|security\\.debian\\.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources; \
    else \
        sed -i -e 's|http://deb.debian.org/debian|https://mirrors.tuna.tsinghua.edu.cn/debian|g' \
               -e 's|http://security.debian.org/debian-security|https://mirrors.tuna.tsinghua.edu.cn/debian-security|g' /etc/apt/sources.list; \
    fi; \
    printf '\nAcquire::Retries \'5\';\nAcquire::http::Pipeline-Depth \'0\';\nAcquire::http::No-Cache \'true\';\n' > /etc/apt/apt.conf.d/99retries

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
