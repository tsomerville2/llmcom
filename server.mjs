import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { once } from 'node:events';
import { startServer } from '@relaycast/engine/node';
import { configDir, stateDir, privateJson, readConfig } from './runtime.mjs';

process.umask(0o077);
fs.mkdirSync(stateDir, { recursive: true, mode: 0o700 });
const secretFile = path.join(configDir, 'server-secret.json');
if (!fs.existsSync(secretFile)) privateJson(secretFile, { bootstrapSecret: crypto.randomBytes(32).toString('hex') });
const { bootstrapSecret } = JSON.parse(fs.readFileSync(secretFile, 'utf8'));
const port = Number(new URL(readConfig().baseUrl).port);
if (!Number.isInteger(port) || port < 1024 || port > 65535) throw new Error('Invalid local relay port');
const running = startServer({
  dbPath: path.join(stateDir, 'relaycast.db'),
  fileDir: path.join(stateDir, 'files'),
  port, baseUrl: `http://127.0.0.1:${port}`,
  config: { environment: 'exp31-private', workspaceBootstrapSecret: bootstrapSecret },
});
// The published entry point does not expose a hostname option. Rebind its returned
// HTTP server to loopback, retaining the engine and WebSocket upgrade handlers.
if (!running.server.listening) await once(running.server, 'listening');
await new Promise((resolve, reject) => running.server.close((error) => error ? reject(error) : resolve()));
running.server.listen(port, '127.0.0.1');
await once(running.server, 'listening');
console.log(`Relaycast ready on 127.0.0.1:${port}`);
for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, () => {
  void running.stop().then(() => process.exit(0));
});
