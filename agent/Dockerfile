FROM python:3.14-slim

RUN apt-get update \
    && apt-get install --no-install-recommends -y tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY *.py ./

ENV PYTHONUNBUFFERED=1 \
    STEAM_LOG_PATH=/steam-logs/gameprocess_log.txt \
    AGENT_DATA_DIR=/data

CMD ["python", "main.py"]
