FROM node:22-alpine

WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm ci

# Copy source and build production bundle (Vite -> dist/)
COPY . .
RUN npm run build

# Serve static SPA
RUN npm install -g serve

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -qO- http://localhost:3000/ > /dev/null || exit 1

CMD ["serve", "-s", "dist", "-l", "3000"]
