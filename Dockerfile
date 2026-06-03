FROM python:3.12-slim

LABEL org.opencontainers.image.title="HarnessCI"
LABEL org.opencontainers.image.description="CI for AI-generated Pull Requests"
LABEL org.opencontainers.image.source="https://github.com/Jairogelpi/HarnessCI"
LABEL org.opencontainers.image.licenses="MIT"

# Install git (required for git diff inside the action)
RUN apt-get update && apt-get install -y --no-install-recommends git curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python package
COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --no-cache-dir -e "." \
    && pip install --no-cache-dir requests

# Copy entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
