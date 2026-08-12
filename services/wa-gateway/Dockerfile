FROM node:20-alpine AS deps
WORKDIR /app
COPY services/wa-gateway/package.json ./
RUN npm install

FROM node:20-alpine
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY services/wa-gateway/src ./src
COPY services/wa-gateway/package.json ./
ENV NODE_ENV=production
EXPOSE 8100
CMD ["npm", "start"]