FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV MEETING_AGENT_CONFIG_PATH=/app/config.docker.yaml

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
COPY requirements-diarization.txt /app/requirements-diarization.txt
ARG INSTALL_DIARIZATION=false
RUN python -m pip install --upgrade pip \
    && python -m pip install -r /app/requirements.txt \
    && if [ "$INSTALL_DIARIZATION" = "true" ]; then python -m pip install -r /app/requirements-diarization.txt; fi

COPY . /app

EXPOSE 8000

CMD ["python", "scripts/asu_june_bot_api.py", "--host", "0.0.0.0", "--port", "8000"]
