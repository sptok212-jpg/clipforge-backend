FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    unzip \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# yt-dlp needs an external JS runtime to solve YouTube's JS challenges
# (required since yt-dlp 2025.11.12). Deno is the default/recommended
# runtime and installs as a single self-contained binary.
ENV DENO_INSTALL=/usr/local
RUN curl -fsSL https://deno.land/install.sh | sh -s -- -y

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
