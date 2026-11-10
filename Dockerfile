# One container for the whole app: the React screens are built first,
# then served by the FastAPI backend together with the API.

FROM node:20-slim AS screens
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=screens /app/frontend/dist /app/frontend/dist
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser
# Render sets PORT; 8000 when running the container by hand
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
