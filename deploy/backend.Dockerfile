# VisionX backend (FastAPI) – production image
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ffmpeg for audio/video, libGL/glib for OpenCV, compiler for packages without prebuilt wheels
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libgl1 libglib2.0-0 build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# CPU-only PyTorch first (the default wheel pulls ~2 GB of CUDA libraries)
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision

COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

COPY backend/ backend/

RUN useradd --create-home --uid 1000 app && mkdir -p /app/storage && chown -R app:app /app
USER app

EXPOSE 8000
# One worker: analyses run as in-process background tasks
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
