# syntax=docker/dockerfile:1
#
# Prod image for the TiranaTips API + events ingestion.
# Layer order is deliberate: dependencies (slow, rarely change) come BEFORE the
# code COPY (fast, changes constantly). On a code-only deploy, Docker reuses the
# cached dependency layers — including the heavy Chromium install — and only
# rebuilds the final COPY. The expensive Chromium layer is paid once, and again
# only when requirements.txt changes.

FROM python:3.11-slim

WORKDIR /app

# Python deps first (cached unless requirements.txt changes).
COPY requirements.txt .

# CPU-only PyTorch FIRST, from PyTorch's dedicated index. sentence-transformers
# pulls torch transitively, and the default PyPI torch wheel bundles the entire
# CUDA stack (nvidia-cublas, cudnn, nccl, triton — ~5-7GB) which is useless on a
# CPU VPS and overflows the disk during build. Installing the CPU build first
# means the requirements install below finds torch already satisfied and skips
# the CUDA wheels entirely.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir -r requirements.txt

# Playwright's Chromium + its system libraries. `--with-deps` pulls the OS
# packages (libnss3, fonts, etc.) that a bare slim image lacks, so we don't
# hand-maintain an apt list. This is the big layer; it sits above the code COPY
# so it stays cached across normal deploys.
RUN playwright install --with-deps chromium

# Application code last — this is the layer that rebuilds on every push.
COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]