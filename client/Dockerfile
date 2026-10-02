# syntax=docker/dockerfile:1.7

FROM node:22-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# Build with client env mounted as a BuildKit secret (never baked into image layers as a COPY).
# Compose: secrets.client_env -> file ./client/.env
RUN --mount=type=secret,id=client_env,target=/app/.env,required=false \
    npm run build

RUN npm install -g serve

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -qO- http://localhost:3000/ > /dev/null || exit 1

CMD ["serve", "-s", "dist", "-l", "3000", "--config", "dist/serve.json"]
