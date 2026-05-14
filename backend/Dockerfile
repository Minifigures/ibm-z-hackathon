# Code Engine: FastAPI backend container
# Build context: backend/
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install runtime deps first to take advantage of layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Application code.
COPY app ./app

# Code Engine maps the public port to whatever your app listens on. 8000 is
# the historical port for this project so the env stays consistent.
EXPOSE 8000

# uvicorn binds to all interfaces so Code Engine's proxy can reach us.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
