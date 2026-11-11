# Panel ComplianceAI (Next.js 15, salida standalone)
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

FROM node:22-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# NEXT_PUBLIC_* se fija en tiempo de build
ARG NEXT_PUBLIC_DEMO=0
ENV NEXT_PUBLIC_DEMO=$NEXT_PUBLIC_DEMO
# API_URL se lee al construir los rewrites; en compose es el servicio "api"
ARG API_URL=http://api
ENV API_URL=$API_URL
ENV NEXT_TELEMETRY_DISABLED=1
# next/font/google descarga Inter y Space Grotesk desde Google Fonts AL COMPILAR. A veces
# Google responde con direcciones de fuente sin extensión y Next 15.5 se cae con
# "TypeError: Cannot read properties of null (reading '1')" en @next/font/.../loader.js
# (falla intermitente conocida, vercel/next.js#99114). Se reintenta hasta 3 veces; la
# solución definitiva es servir las fuentes desde el repositorio con next/font/local.
RUN for intento in 1 2 3; do \
      npm run build && exit 0; \
      echo "next build falló (intento $intento de 3); reintento en 20 s..."; sleep 20; \
    done; exit 1

FROM node:22-alpine AS run
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -S app && adduser -S app -G app
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
USER app
EXPOSE 3000
CMD ["node", "server.js"]
