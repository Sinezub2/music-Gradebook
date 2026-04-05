FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl unzip \
    && useradd --create-home --home-dir /home/sysuser --shell /bin/sh sysuser \
    && mkdir -p /home/sysuser/music-Gradebook \
    && chown -R sysuser:sysuser /home/sysuser \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /home/sysuser/music-Gradebook

COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

COPY docker/entrypoint.sh /usr/local/bin/music-gradebook-entrypoint
RUN chmod +x /usr/local/bin/music-gradebook-entrypoint

COPY --chown=sysuser:sysuser . /home/sysuser/music-Gradebook

USER sysuser
