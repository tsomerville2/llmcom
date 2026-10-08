FROM node:22.23.0-alpine
WORKDIR /app
COPY package*.json ./
RUN apk add --no-cache su-exec && npm ci --omit=dev && mkdir /data && chown node:node /data
COPY server.mjs oauth.mjs entrypoint.sh setup.html install.sh ./
COPY images ./images
ENV PORT=8080 DATA_DIR=/data
EXPOSE 8080
CMD ["sh", "entrypoint.sh"]
