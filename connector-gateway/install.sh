#!/bin/sh
set -eu
if [ "$(uname -s)" != Darwin ]; then
  echo 'LLMCom phone setup currently supports macOS. See https://llmcom-connector.fly.dev/setup' >&2
  exit 1
fi
if command -v uv >/dev/null 2>&1; then
  llmcom_uv=$(command -v uv)
elif [ -x "$HOME/.local/bin/uv" ]; then
  llmcom_uv="$HOME/.local/bin/uv"
else
  echo 'Installing uv from its official installer...'
  curl -fsSL https://astral.sh/uv/install.sh | sh
  llmcom_uv="$HOME/.local/bin/uv"
fi
echo 'Installing LLMCom from PyPI...'
"$llmcom_uv" tool install --upgrade --force --refresh --index-url https://pypi.org/simple 'llmcom>=0.4.10'
echo 'Preparing this Mac and printing next steps...'
exec "$llmcom_uv" tool run --refresh --index-url https://pypi.org/simple --from 'llmcom>=0.4.10' llmcom --setup "$@"
