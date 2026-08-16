# ---- deps ----
FROM node:20-alpine AS deps
RUN apk add --no-cache git
WORKDIR /app
COPY services/web/package.json services/web/package-lock.json* ./
RUN npm install

# ---- build ----
FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY services/web .
RUN npm run build

# ---- runtime ----
FROM node:20-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/public ./public
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/next.config.mjs ./
EXPOSE 3000
CMD ["npm", "start"]