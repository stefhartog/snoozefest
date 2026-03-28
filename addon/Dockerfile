ARG BUILD_FROM=ghcr.io/home-assistant/base:latest

FROM ${BUILD_FROM}

# Install Python build essentials and dependencies
RUN apk add --no-cache \
    python3 \
    py3-pip \
    build-base \
    python3-dev

# Copy application code
COPY . /app
WORKDIR /app

# Install snoozefest and dependencies
RUN pip install --no-cache-dir -e .

# Run the daemon
CMD ["snoozefest", "--config", "/config/snoozefest.json", "run"]
