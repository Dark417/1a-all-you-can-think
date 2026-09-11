# Multi-stage, small, non-root image -- production hygiene the manifests rely on
# (the Pod securityContext runs as this UID and drops privileges).
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install deps first for better layer caching.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY main.py .

# Run as an unprivileged user (uid 10001). Matches runAsUser in the Deployment.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin appuser
USER 10001

EXPOSE 8000

# 1 worker per container; scale by adding Pods, not threads (let Kubernetes do it).
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
