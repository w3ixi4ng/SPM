# Two stages. The build needs Node and the whole dependency tree; the runtime
# needs neither -- only nginx and the static bundle Vite emits.

FROM node:22-alpine AS build

WORKDIR /app

# Manifests first, so the dependency layer stays cached when only source
# changes. `npm ci` installs exactly what package-lock.json pins, which is what
# makes a CI build reproducible.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

# Not published in docker-compose.yml on purpose. The app calls a relative
# /api, so it is only correct behind Kong -- see the comment on the service.
EXPOSE 80
