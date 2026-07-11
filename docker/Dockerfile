# CI image with every pipeline dependency preinstalled, so sharded jobs skip the
# ~60-90s apt/pip/chrome setup and shard fan-out (up to 20 workers) stays cheap.
FROM python:3.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    FFMPEG_BIN=ffmpeg FFPROBE_BIN=ffprobe \
    PDFTOPPM_BIN=pdftoppm PDFINFO_BIN=pdfinfo \
    CHROME_BIN=/usr/bin/chromium

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg poppler-utils chromium \
        fonts-liberation fonts-dejavu-core \
        ca-certificates curl git git-lfs \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
         -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
         > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir edge-tts

# node is needed for GitHub JS actions (checkout/cache/artifact) inside container jobs
RUN apt-get update && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*
