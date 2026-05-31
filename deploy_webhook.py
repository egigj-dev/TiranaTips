#!/usr/bin/env python3
"""
GitHub Webhook listener for auto-deploy on push to main.

Listens on port 9000, validates HMAC-SHA256 signature, then runs:
    git fetch origin main
    git reset --hard origin/main
    docker compose restart api

Why fetch+reset instead of pull?
    `git pull` = fetch + merge. Merge fails on local changes or conflicts,
    leaving the server in a half-deployed state. `reset --hard` forces the
    working tree to exactly match origin/main — the right primitive for a
    one-way production mirror.
"""
import os
import hmac
import json
import logging
import subprocess
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(REPO_DIR, "deploy.log")
SECRET   = os.environ.get("DEPLOY_WEBHOOK_SECRET", "")
PORT     = int(os.environ.get("DEPLOY_WEBHOOK_PORT", 9000))

# A single global lock prevents two pushes arriving in quick succession from
# running two `git reset` + `docker restart` cycles in parallel. The second
# webhook just logs "deploy already in progress" and returns — GitHub will
# show it as delivered, which is what we want.
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


def _run(cmd: list[str], step: str) -> bool:
    """Run a subprocess, log its output, return True on success."""
    logger.info("%s: %s", step, " ".join(cmd))
    try:
        result = subprocess.run(
            cmd, cwd=REPO_DIR,
            capture_output=True, text=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        logger.error("%s: timed out after 120s", step)
        return False

    if result.stdout:
        logger.info("%s stdout:\n%s", step, result.stdout.rstrip())
    if result.stderr:
        # git/docker write a lot of normal output to stderr — log as info,
        # only the non-zero exit code marks real failure.
        logger.info("%s stderr:\n%s", step, result.stderr.rstrip())

    if result.returncode != 0:
        logger.error("%s failed with exit code %d", step, result.returncode)
        return False
    return True


def _run_deploy() -> None:
    """Force the working tree to origin/main and restart the API container."""
    if not _deploy_lock.acquire(blocking=False):
        logger.warning("Deploy already in progress — skipping this trigger")
        return

    try:
        logger.info("=== Starting deploy ===")
        if not _run(["git", "fetch", "origin", "main"], "git fetch"):
            return
        if not _run(["git", "reset", "--hard", "origin/main"], "git reset"):
            return
        if not _run(["docker", "compose", "restart", "api"], "docker restart"):
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
            # Fail closed: refuse to deploy without a configured secret.
            # The original version failed *open* here, which means anyone
            # who could reach port 9000 could trigger a deploy.
            logger.error("DEPLOY_WEBHOOK_SECRET not set — refusing request")
            return False

        sig_header = self.headers.get("X-Hub-Signature-256", "")
        if not sig_header.startswith("sha256="):
            logger.warning("Missing or malformed X-Hub-Signature-256 header")
            return False

        expected = "sha256=" + hmac.new(SECRET.encode(), body, "sha256").hexdigest()
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
            # Reply to GitHub immediately (10s timeout on their side),
            # do the actual work in a background thread.
            threading.Thread(target=_run_deploy, daemon=True).start()
            self._reply(200, b"Deploy triggered")
            return

        logger.info("Ignoring event type: %s", event)
        self._reply(200, b"Ignored")


def main():
    if not SECRET:
        logger.warning(
            "DEPLOY_WEBHOOK_SECRET is not set — ALL requests will be rejected. "
            "Set it in .env or export it before starting this service."
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