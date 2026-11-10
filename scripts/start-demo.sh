#!/usr/bin/env bash
# Reuse the installed local stack; never downloads models or changes credentials.
set -euo pipefail
repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
node_runtime="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin"
if [ -d "$node_runtime" ]; then export PATH="$node_runtime:$PATH"; fi
if [ -d /Applications/Docker.app/Contents/Resources/bin ]; then
  export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
fi
command -v node >/dev/null || { echo "Node.js is missing."; exit 1; }
command -v pnpm >/dev/null || { echo "pnpm is missing."; exit 1; }
docker info >/dev/null 2>&1 || { echo "Open Docker Desktop, wait until it is running, then retry."; exit 1; }
cd "$repo_dir/apps/web"
node --input-type=module <<'JS'
import {loadEnvFile} from 'node:process';
loadEnvFile('.env.local');
if ((process.env.CLAIM_CHAT_PROVIDER || 'ollama') === 'ollama') {
  try {
    const response = await fetch('http://127.0.0.1:11434/api/tags', {signal: AbortSignal.timeout(5000)});
    const data = await response.json();
    const model = process.env.OLLAMA_MODEL || 'gemma4:12b';
    if (!data.models?.some(item => item.name === model)) throw new Error('model');
  } catch {
    console.error('Open Ollama and ensure the configured model is installed, then retry.');
    process.exit(1);
  }
}
JS
pnpm --config.verify-deps-before-run=false run check:local
if [ "${1:-}" = "--check" ]; then exit 0; fi
exec pnpm --config.verify-deps-before-run=false run dev:local
