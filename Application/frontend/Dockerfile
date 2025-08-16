# ---------- Stage 1: Build ----------
FROM node:18 AS builder
WORKDIR /app
COPY package*.json ./
RUN npm install --silent
COPY . .

# ---------- Stage 2: Production Image ----------
FROM node:18-alpine AS production
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY --from=builder /app ./
EXPOSE 3000
CMD ["npm", "start"]
