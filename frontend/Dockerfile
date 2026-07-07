# syntax=docker/dockerfile:1
#
# Frontend image for TiranaTips — multi-stage:
#   stage 1 (build): Node compiles the Vite bundle into static files
#   stage 2 (serve): nginx serves those files + proxies API calls to the
#                    `api` container over the internal compose network.
#
# Node never reaches the final image or the VPS host — same "deps baked into
# the image, host stays clean" discipline as the backend Dockerfile.

# ── Stage 1: build the static bundle ───────────────────────────────────────
# node:22 — Vite 8 requires Node 20.19+/22.12+; 22-alpine is small and current.
FROM node:22-alpine AS build
WORKDIR /app

# Dependencies first (cached unless the lockfile changes), mirroring the
# backend's layer ordering. `npm ci` installs strictly from package-lock.json
# for a reproducible build — the right primitive for an image.
COPY package.json package-lock.json ./
RUN npm ci

# Source, then build. `npm run build` runs in production mode, so it reads
# .env.production (if present) — NOT .env.development. With nginx proxying the
# API same-origin, VITE_API_BASE is left unset and api.js falls back to "".
#
# VITE_GOOGLE_MAPS_KEY must come in as a build arg: Vite inlines
# import.meta.env.* at build time, and this stage never sees the compose
# .env file. Without it, MapPanel's `if (!key) return` guard fires and
# Rolldown tree-shakes the maps code out of the bundle entirely.
ARG VITE_GOOGLE_MAPS_KEY
ENV VITE_GOOGLE_MAPS_KEY=$VITE_GOOGLE_MAPS_KEY
COPY . .
RUN npm run build

# ── Stage 2: serve with nginx ──────────────────────────────────────────────
FROM nginx:1.27-alpine

# Our SPA + API-proxy config replaces nginx's default site.
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Only the compiled output crosses the stage boundary.
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
# nginx:alpine's default CMD already runs `nginx -g 'daemon off;'`.
