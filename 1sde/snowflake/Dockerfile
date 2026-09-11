FROM python:3.11-slim

WORKDIR /app

# Install deps first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# The catalog connects to MongoDB via MONGO_URI (see docker-compose.yml); if it
# is unreachable the app degrades gracefully to an in-memory mongomock.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
