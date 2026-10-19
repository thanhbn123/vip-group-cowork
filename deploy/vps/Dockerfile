FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd -g 10001 cowork && useradd -u 10001 -g 10001 -m cowork

RUN pip install --no-cache-dir \
    "fastapi>=0.115" "uvicorn>=0.30" "jinja2>=3.1" \
    "python-multipart>=0.0.20" "httpx>=0.27"

COPY cowork ./cowork
COPY run.sh ./run.sh
RUN chmod 755 ./run.sh

USER cowork
EXPOSE 8899

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8899/api/health', timeout=3).status==200 else 1)"

CMD ["python", "-m", "uvicorn", "cowork.main:app", \
     "--host", "0.0.0.0", "--port", "8899", \
     "--no-access-log", "--no-proxy-headers"]
