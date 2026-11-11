FROM node:20-bookworm-slim AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY rp-base-path.inc /etc/nginx/conf.d/rp-base-path.inc
COPY docker-entrypoint.d/40-rp-base-path.sh /docker-entrypoint.d/40-rp-base-path.sh
# Git on Windows may check out shell scripts with CRLF; nginx runs /bin/sh.
RUN sed -i 's/\r$//' /docker-entrypoint.d/40-rp-base-path.sh && chmod +x /docker-entrypoint.d/40-rp-base-path.sh
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
