# ---- Stage 1: Build frontend ----
FROM node:22-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ARG VITE_API_BASE=/api
ENV VITE_API_BASE=$VITE_API_BASE
RUN npm run build

# ---- Stage 2: Python backend ----
FROM python:3.12-slim
WORKDIR /app

# Install Python dependencies (core only — no langchain/playwright to stay under free tier limits)
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

# Copy application code
COPY backend/ ./backend/
COPY knowledge_graph/ ./knowledge_graph/
COPY data/ ./data/

# Copy frontend build from stage 1
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
