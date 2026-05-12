FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN useradd --create-home --home-dir /home/sysuser --shell /bin/sh sysuser \
    && mkdir -p /home/sysuser/music-Gradebook \
    && chown -R sysuser:sysuser /home/sysuser

WORKDIR /home/sysuser/music-Gradebook

COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

COPY --chown=sysuser:sysuser . /home/sysuser/music-Gradebook
RUN chmod +x /home/sysuser/music-Gradebook/docker/start-web.sh

USER sysuser
