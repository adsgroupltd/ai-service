# -------------------------------------------------
# Build the React app with Vite (Node 20 Alpine)
# -------------------------------------------------
FROM node:20-alpine AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

COPY index.html vite.config.js tsconfig.json ./
COPY src ./src

RUN npm run build   # creates ./dist

# -------------------------------------------------
# Serve the static files with a tiny nginx
# -------------------------------------------------
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
