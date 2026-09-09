FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    LETTERMATCH_DB=/data/lettermatch.db

WORKDIR /app

COPY requirements.txt .
# --trusted-host keeps the build working behind a TLS-inspecting corporate proxy
# whose root CA the base image doesn't ship. Drop these flags if you don't need them.
RUN pip install --no-cache-dir --disable-pip-version-check \
    --trusted-host pypi.org \
    --trusted-host files.pythonhosted.org \
    --trusted-host pypi.python.org \
    -r requirements.txt

COPY app ./app

RUN mkdir -p /data
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
