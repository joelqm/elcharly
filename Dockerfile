FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TZ=America/Lima
ENV LANG=es_PE.UTF-8
ENV LC_ALL=es_PE.UTF-8
ENV PYTHONIOENCODING=utf-8

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/

EXPOSE 8090

CMD ["gunicorn", "proyecto_makita.wsgi:application", "--bind", "0.0.0.0:8090", "--workers", "3"]
