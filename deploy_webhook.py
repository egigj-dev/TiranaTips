#!/usr/bin/env python3
"""
GitHub Webhook listener for auto-deploy on push to main.

Listens on port 9000, validates HMAC-SHA256 signature, then runs:
    git fetch origin main
    git reset --hard origin/main
    docker compose -f docker-compose.yml build api
    docker compose -f docker-compose.yml up -d --force-recreate api

Why fetch+reset instead of pull?
    `git pull` = fetch + merge. Merge fails on local changes or conflicts,
    leaving the server in a half-deployed state. `reset --hard` forces the
    working tree to exactly match origin/main — the right primitive for a
    one-way production mirror.

Why build then recreate?
    Code is baked into the image (see Dockerfile), so the running container
    serves the image's copy — not the host files. A plain restart/recreate
    would re-run the OLD image. `build` re-bakes code+deps into a new image
    (reusing cached layers, so the Chromium layer is only rebuilt when
    requirements.txt changes), then force-recreate swaps the container onto it.

Why `-f docker-compose.yml`?
    Pins the prod compose file so docker-compose.override.yml (the dev-only
    bind mount) is NOT merged. Prod runs purely from the baked image.
"""
import os
import hmac
import json
import hashlib
import logging
import subprocess
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(REPO_DIR, "deploy.log")
SECRET   = os.environ.get("DEPLOY_WEBHOOK_SECRET", "")
PORT     = int(os.environ.get("DEPLOY_WEBHOOK_PORT", 9000))

# A single global lock prevents two pushes arriving in quick succession from
# running two deploy cycles in parallel. The second webhook just logs
# "deploy already in progress" and returns 200 — GitHub marks it delivered.
_deploy_lock = threading.Lock()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("deploy-webhook")


def _run(cmd: list[str], step: str, timeout: int = 120) -> bool:
    """Run a subprocess, log its output, return True on success."""
    logger.info("%s: %s", step, " ".join(cmd))
    try:
        result = subprocess.run(
            cmd, cwd=REPO_DIR,
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        logger.error("%s: timed out after %ds", step, timeout)
        return False

    if result.stdout:
        logger.info("%s stdout:\n%s", step, result.stdout.rstrip())
    if result.stderr:
        # git/docker write normal progress to stderr — log as info,
        # only non-zero exit code marks real failure.
        logger.info("%s stderr:\n%s", step, result.stderr.rstrip())

    if result.returncode != 0:
        logger.error("%s failed with exit code %d", step, result.returncode)
        return False
    return True


def _run_deploy() -> None:
    """Force the working tree to origin/main and recreate the API container."""
    if not _deploy_lock.acquire(blocking=False):
        logger.warning("Deploy already in progress — skipping this trigger")
        return

    try:
        logger.info("=== Starting deploy ===")
        if not _run(["git", "fetch", "origin", "main"], "git fetch"):
            return
        if not _run(["git", "reset", "--hard", "origin/main"], "git reset"):
            return
        # Code is baked into the image now, so a plain recreate would run the
        # OLD image. We must rebuild. `-f docker-compose.yml` bypasses the dev
        # override (docker-compose.override.yml) so prod never mounts host code.
        # Long timeout: a cold build installs Chromium; warm builds reuse the
        # cached layer and finish fast.
        if not _run(
            ["docker", "compose", "-f", "docker-compose.yml", "build", "api"],
            "docker build", timeout=900,
        ):
            return
        if not _run(
            ["docker", "compose", "-f", "docker-compose.yml",
             "up", "-d", "--force-recreate", "api"],
            "docker recreate"
        ):
            return
        logger.info("=== Deploy completed successfully ===")
    finally:
        _deploy_lock.release()


class DeployHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        logger.info("HTTP %s", format % args)

    def _verify_signature(self, body: bytes) -> bool:
        """Verify GitHub's HMAC-SHA256 signature against the raw request body."""
        if not SECRET:
            logger.error("DEPLOY_WEBHOOK_SECRET not set — refusing request")
            return False

        sig_header = self.headers.get("X-Hub-Signature-256", "")
        if not sig_header.startswith("sha256="):
            logger.warning("Missing or malformed X-Hub-Signature-256 header")
            return False

        expected = "sha256=" + hmac.new(
            SECRET.encode(), body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(sig_header, expected)

    def _reply(self, code: int, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)

        if not self._verify_signature(body):
            self._reply(401, b"Invalid signature")
            return

        try:
            payload = json.loads(body)
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON payload: %s", e)
            self._reply(400, b"Invalid JSON")
            return

        event = self.headers.get("X-GitHub-Event", "")
        logger.info("Received event: %s", event)

        if event == "ping":
            self._reply(200, b"pong")
            return

        if event == "push":
            ref = payload.get("ref", "")
            if ref != "refs/heads/main":
                logger.info("Push to '%s' — ignoring (not main)", ref)
                self._reply(200, b"Ignored (not main)")
                return
            # Reply to GitHub immediately (they have a 10s timeout),
            # run the actual deploy in a background thread.
            threading.Thread(target=_run_deploy, daemon=True).start()
            self._reply(200, b"Deploy triggered")
            return

        logger.info("Ignoring event type: %s", event)
        self._reply(200, b"Ignored")


def main():
    if not SECRET:
        logger.warning(
            "DEPLOY_WEBHOOK_SECRET is not set — ALL requests will be rejected. "
            "Set DEPLOY_WEBHOOK_SECRET in .env before starting this service."
        )

    server = HTTPServer(("0.0.0.0", PORT), DeployHandler)
    logger.info("=== Deploy webhook starting on port %d ===", PORT)
    logger.info("Repo:    %s", REPO_DIR)
    logger.info("Logfile: %s", LOG_FILE)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()