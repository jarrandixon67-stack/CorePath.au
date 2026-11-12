FROM python:3.12-slim
WORKDIR /app
COPY backend/ /app/backend/
COPY database/ /app/database/
COPY persy/database/ /app/persy/database/
COPY life-profile/database/ /app/life-profile/database/
RUN pip install --no-cache-dir /app/backend && useradd --create-home corepath
USER corepath
WORKDIR /app/backend
ENV PYTHONUNBUFFERED=1
# Each Render service overrides this command with its own module; no secrets in the image.
CMD ["sh", "-c", "uvicorn persy.main:app --host 0.0.0.0 --port ${PORT:-8000} --no-access-log"]
