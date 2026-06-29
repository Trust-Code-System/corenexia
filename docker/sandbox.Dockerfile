# Corenexia sandbox image — the trusted base for executing untrusted, AI-generated code.
# Containers built from this image are run by app/sandbox/docker_runner.py with hardening
# flags (no network, dropped caps, read-only rootfs, non-root, resource limits) and are
# destroyed after every single execution.
FROM python:3.11-slim

# Pre-install the libraries the orchestrator commonly needs for legal/finance work so the
# generated scripts don't have to (and can't — the container has no network).
RUN pip install --no-cache-dir \
        pdfplumber==0.11.4 \
        python-docx==1.1.2 \
        pandas==2.2.3 \
        numpy==2.1.3

# Code is delivered to the container over stdin (`python -`); see DockerRunner.
# A non-login, unprivileged default. The runner additionally pins --user 65534.
WORKDIR /sandbox
CMD ["python", "-"]
