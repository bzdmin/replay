# Replay runs anywhere that can run a container.
#
# The port is taken from $PORT so the same image works on Hugging Face Spaces
# (7860), Fly, Cloud Run, ECS, or a laptop.

FROM python:3.12-slim

# Hugging Face Spaces runs containers as uid 1000, so build for that rather
# than root; the image then behaves the same locally and on the Space.
RUN useradd -m -u 1000 user

WORKDIR /app

COPY --chown=user:user requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

COPY --chown=user:user . .

USER user

ENV PORT=7860 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/home/user \
    AWS_REGION=us-east-1

EXPOSE 7860

# A rehearsal spawns real subprocesses and can run for a couple of minutes, so
# keep a single worker and a generous keep-alive for the progress stream.
CMD ["sh", "-c", "uvicorn replay.web:app --host 0.0.0.0 --port ${PORT:-7860} --workers 1 --timeout-keep-alive 120"]
