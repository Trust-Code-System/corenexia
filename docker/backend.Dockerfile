# Corenexia backend image.
#
# NOTE: the backend shells out to the `docker` CLI to create ephemeral sandbox containers, so a
# containerized backend needs (a) the Docker client binary, installed below, and (b) access to a
# Docker daemon — e.g. the host socket mounted by docker-compose, or a remote daemon. Treat
# granting Docker access as a deliberate, security-sensitive decision (see docker-compose.yml).
FROM python:3.11-slim

# Docker CLI (client only — no daemon) so the backend can run `docker run` against a mounted/remote
# daemon. Pinned static binary keeps the image slim. Override DOCKER_CLI_VERSION/ARCH for arm64.
ARG DOCKER_CLI_VERSION=27.5.1
ARG DOCKER_CLI_ARCH=x86_64
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends curl ca-certificates; \
    curl -fsSL "https://download.docker.com/linux/static/stable/${DOCKER_CLI_ARCH}/docker-${DOCKER_CLI_VERSION}.tgz" \
      | tar -xz -C /usr/local/bin --strip-components=1 docker/docker; \
    apt-get purge -y --auto-remove curl; \
    rm -rf /var/lib/apt/lists/*; \
    docker --version

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./

EXPOSE 8000
# Simple container healthcheck against /health (no curl in the final image — use Python).
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=3).status==200 else 1)"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
