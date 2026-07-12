FROM python:3.12-slim

ARG APP_UID=10001
ARG APP_GID=10001

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV MEETING_AGENT_CONFIG_PATH=/app/config.docker.yaml
ENV HOME=/app/data/home
ENV XDG_CACHE_HOME=/app/data/.cache
ENV HF_HOME=/app/data/.cache/huggingface

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid "${APP_GID}" meetingagent \
    && useradd --uid "${APP_UID}" --gid "${APP_GID}" --create-home \
        --shell /usr/sbin/nologin meetingagent

COPY requirements.txt /app/requirements.txt
COPY requirements-transcription.txt /app/requirements-transcription.txt
COPY constraints-py312.txt /app/constraints-py312.txt
COPY requirements-diarization.txt /app/requirements-diarization.txt
ARG INSTALL_DIARIZATION=false
RUN python -m pip install -c /app/constraints-py312.txt pip \
    && python -m pip install -c /app/constraints-py312.txt \
        -r /app/requirements.txt \
        -r /app/requirements-transcription.txt \
    && if [ "$INSTALL_DIARIZATION" = "true" ]; then python -m pip install -c /app/constraints-py312.txt -r /app/requirements-diarization.txt; fi

COPY src /app/src
COPY scripts /app/scripts
COPY configs /app/configs
COPY config.docker.yaml /app/config.docker.yaml

RUN install -d -o meetingagent -g meetingagent \
        /app/data \
        /app/data/.cache \
        /app/data/home \
        /app/logs \
        /app/meetings \
        /app/models \
        /app/vector_db \
        /app/watched_folder

USER meetingagent:meetingagent

EXPOSE 8000

ENTRYPOINT ["python", "scripts/docker_entrypoint.py"]
CMD ["python", "scripts/asu_june_bot_api.py", "--host", "0.0.0.0", "--port", "8000"]
