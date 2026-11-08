# AI Stock Sentiment Agent — frontend image
# Pinned: Node.js 22 (build stage), nginx:alpine (serve stage).
# The compiled bundle is fully static; /api/ is proxied to the backend
# service by nginx.conf at runtime (no host addresses in the bundle).

# ---------- stage 1: build ----------
FROM node:22-alpine AS builder
WORKDIR /build
# Copy manifests first so the install layer is cached and reproducible.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- stage 2: serve ----------
FROM nginx:alpine
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /build/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
  CMD wget -qO- http://127.0.0.1/ >/dev/null 2>&1 || exit 1
CMD ["nginx", "-g", "daemon off;"]
