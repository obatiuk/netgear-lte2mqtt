# syntax=docker/dockerfile:1

# Builder stage to install dependencies
FROM registry.access.redhat.com/hi/python:3.14-builder AS builder

USER root

WORKDIR /app

# Create virtual environment, install dependencies without bytecode, and strip pip to minimize runtime footprint
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,source=requirements.txt,target=requirements.txt \
    python3 -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-compile --disable-pip-version-check -r requirements.txt && \
    /opt/venv/bin/pip uninstall -y pip

# Final hardened stage
FROM registry.access.redhat.com/hi/python:3.14

LABEL org.opencontainers.image.source="https://github.com/obatiuk/netgear-lte2mqtt" \
      org.opencontainers.image.description="Netgear LTE modem status to MQTT bridge" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Copy installed virtual environment from builder stage
COPY --from=builder --chown=65532:65532 /opt/venv /opt/venv

# Copy source code as a package
COPY --chown=65532:65532 src/ ./src/

USER 65532

# Healthcheck to verify the service started and is running
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=2 \
    CMD ["python3", "-m", "netgear_lte2mqtt.main", "--healthcheck"]

# Run the application as a module to ensure correct import behavior
CMD ["python3", "-u", "-m", "netgear_lte2mqtt.main"]
