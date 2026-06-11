FROM python:3.11-slim

# Install system dependencies (git, curl, build essentials for standard tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create workspace directory inside container for safe operations
RUN mkdir -p /workspace
ENV WORKSPACE_ROOT=/workspace
ENV LLM_API_URL=http://host.docker.internal:8080/v1/chat/completions
ENV LLM_MODEL=lfm-2.5-8b

# Copy app code
COPY app/ ./app/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
