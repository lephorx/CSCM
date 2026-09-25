FROM node:24-alpine AS dependencies

WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

FROM dependencies AS build
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm build

FROM node:24-alpine
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000

RUN addgroup -S cscm && adduser -S cscm -G cscm
COPY --from=build --chown=cscm:cscm /app/public ./public
COPY --from=build --chown=cscm:cscm /app/.next/standalone ./
COPY --from=build --chown=cscm:cscm /app/.next/static ./.next/static
USER cscm

EXPOSE 3000
CMD ["node", "server.js"]
