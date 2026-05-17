# Copyright 2026 Clark Labs Inc. — MIT
#
# clark-browser in a container for a ready-to-go stealth-Chromium environment.
#
# Image size: ~750 MB (Chromium binary + system libs + Python runtime).

FROM python:3.12-slim

# Chromium system deps + Node (for agent-browser integration)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdbus-1-3 libdrm2 libxkbcommon0 libatspi2.0-0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 libx11-xcb1 libfontconfig1 libx11-6 \
    libxcb1 libxext6 libxshmfence1 \
    libglib2.0-0 libgtk-3-0 libpangocairo-1.0-0 libcairo-gobject2 \
    libgdk-pixbuf-2.0-0 libxss1 libxtst6 fonts-liberation \
    fonts-noto-color-emoji fonts-unifont fonts-freefont-ttf \
    fonts-ipafont-gothic fonts-wqy-zenhei fonts-tlwg-loma-otf \
    xvfb xdotool curl ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python wrapper
COPY pyproject.toml README.md LICENSE CHANGELOG.md ./
COPY clarkbrowser/ clarkbrowser/
RUN pip install --no-cache-dir ".[serve]"

# CLI shortcuts
COPY bin/clarkserve /usr/local/bin/clarkserve
RUN chmod +x /usr/local/bin/clarkserve

# Pre-download stealth Chromium binary at build time
RUN python -c "from clarkbrowser import ensure_binary; ensure_binary()" || \
    echo "(skipped binary pre-fetch — set CLARK_BINARY_PATH or run again at runtime)"

EXPOSE 9222

# Default: serve CDP on :9222
CMD ["clarkserve", "--port=9222", "--headless=true"]
