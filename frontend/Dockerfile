FROM oven/bun:1.3

WORKDIR /app

COPY package.json bun.lock ./
RUN bun install --frozen-lockfile

COPY . .
# Vite inlines VITE_* at build time; the image has no .env.
ARG VITE_CLERK_PUBLISHABLE_KEY
ARG VITE_API_BASE_URL
RUN bun run build

EXPOSE 3000
CMD ["bun", "run", "preview"]
