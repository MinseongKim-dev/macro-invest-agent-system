# syntax=docker/dockerfile:1
FROM nginx:1.27-alpine

# Remove default nginx config
RUN rm /etc/nginx/conf.d/default.conf

# Copy custom nginx config
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

# Copy static assets
COPY frontend/ /usr/share/nginx/html/

EXPOSE 80
