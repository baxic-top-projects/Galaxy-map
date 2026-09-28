FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV PYTHONPATH=/app
ENV CATALOG_HOST=0.0.0.0
ENV CATALOG_PORT=8003

EXPOSE 8003

HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=10 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8003/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
