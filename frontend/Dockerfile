# ── Stage 1: Build ────────────────────────────────────────────────────────────
FROM oven/bun:1.2 AS builder

WORKDIR /app

# VITE_API_URL is baked in at build time — pass via --build-arg
ARG VITE_API_URL=/api
ENV VITE_API_URL=${VITE_API_URL}

COPY package.json bun.lock ./
RUN bun install

COPY . .
RUN bun run build

# ── Stage 2: Serve with nginx ─────────────────────────────────────────────────
FROM nginx:1.27-alpine AS runner

RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
