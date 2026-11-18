FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_PATH=/data/knowledge.db \
    LOCAL_DATABASE_PATH=/data/knowledge-local.db

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN apt-get update \
    && apt-get install --no-install-recommends -y gosu \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 appuser \
    && useradd --create-home --uid 10001 --gid 10001 appuser \
    && mkdir -p /data \
    && chown appuser:appuser /data \
    && chmod 0700 /data

COPY app ./app
COPY main.py ./main.py
COPY --chown=root:root docker/volume-entrypoint.py /usr/local/bin/volume-entrypoint.py
RUN chmod 0555 /usr/local/bin/volume-entrypoint.py

USER appuser
ENTRYPOINT ["python", "-I", "/usr/local/bin/volume-entrypoint.py"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["/usr/sbin/gosu", "10001:10001", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=3)"]

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
