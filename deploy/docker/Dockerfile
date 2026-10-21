FROM node:22-alpine AS frontend
WORKDIR /ui
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY backend/ ./backend/
COPY cli/ ./cli/
COPY evalscope_sdk/ ./evalscope_sdk/
COPY examples/ ./examples/
COPY datasets/review/ ./datasets/review/
COPY alembic.ini ./
COPY --from=frontend /ui/dist ./frontend/dist
RUN pip install --no-deps . && useradd --create-home --uid 10001 evalscope
USER evalscope
EXPOSE 8000
CMD ["uvicorn", "backend.app.api:app", "--host", "0.0.0.0", "--port", "8000"]
