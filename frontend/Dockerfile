FROM node:20-alpine AS builder
# bust cache on code-only changes
LABEL cache_bust=2

WORKDIR /app
COPY package*.json ./
RUN npm ci --ignore-scripts
COPY . .
RUN node --max-old-space-size=2048 node_modules/.bin/svelte-kit sync && \
    node --max-old-space-size=2048 node_modules/.bin/vite build

FROM node:20-alpine
WORKDIR /app
COPY --from=builder /app/build ./build
COPY --from=builder /app/package.json ./
RUN npm install --omit=dev --ignore-scripts
EXPOSE 3000
ENV NODE_ENV=production
CMD ["node", "build"]
