#!/bin/sh
set -eu
chown node:node /data
chmod 700 /data
exec su-exec node node server.mjs
