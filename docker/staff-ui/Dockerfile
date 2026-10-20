# Crop Sown Registry — Staff Portal UI image.
#
# Same steps as a local build. The image has no .app/ yet, so npm install clones
# staff-ui (deps.json) and applies overrides/. npm run build finds .app/ already
# present, skips the clone, applies overrides/ again, then builds Next.
#
#   docker build -f docker/staff-ui/Dockerfile \
#     -t openg2p/openg2p-cropsown-registry-staff-ui:local .

FROM node:20-alpine AS builder

RUN apk add --no-cache git bash

WORKDIR /open/cropsown-registry/ui/staff-ui

COPY ui/staff-ui/package.json ui/staff-ui/.npmrc ui/staff-ui/deps.json ./
COPY ui/staff-ui/scripts ./scripts
COPY ui/staff-ui/overrides ./overrides

ENV NEXT_TELEMETRY_DISABLED=1
RUN npm install
RUN npm run build \
 && mkdir -p /out \
 && cp -a .app/.next/standalone/. /out/ \
 && cp -a .app/public /out/public \
 && mkdir -p /out/.next \
 && cp -a .app/.next/static /out/.next/static

FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs

COPY --from=builder --chown=nextjs:nodejs /out ./

COPY --chown=nextjs docker/staff-ui/assets/cropsown-prefill-overlay.js /app/public/cropsown-prefill-overlay.js
COPY --chown=nextjs docker/staff-ui/assets/patch-prefill-overlay.js /tmp/patch-prefill-overlay.js
RUN node /tmp/patch-prefill-overlay.js && rm /tmp/patch-prefill-overlay.js

USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
