FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY app ./app
COPY kb ./kb

RUN mkdir -p /app/runs /app/logs /app/cache \
    && useradd --system --create-home --home-dir /home/support-agent support-agent \
    && chown -R support-agent:support-agent /app /home/support-agent

USER support-agent

EXPOSE 8011

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8011/health', timeout=5).read()" || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8011"]
