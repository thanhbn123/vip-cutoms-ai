FROM node:22-alpine
WORKDIR /app
COPY package.json package-lock.json ./
# Optional build secret `ca_bundle` (see apps/api/Dockerfile). Absent/empty → default trust store.
RUN --mount=type=secret,id=ca_bundle,required=false \
    sh -c 'if [ -s /run/secrets/ca_bundle ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/ca_bundle; npm config set cafile /run/secrets/ca_bundle; fi; \
           npm ci --no-audit --no-fund'
COPY . .
EXPOSE 5173
CMD ["npx", "vite", "--host", "0.0.0.0"]
