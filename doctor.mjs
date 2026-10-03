import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import { RelayCast } from '@relaycast/sdk';
import { configDir, stackDir, stateDir, readConfig, credentials } from './runtime.mjs';
import { currentSession, sessionStatus } from './session.mjs';
import { discoverCodexSocket } from './codex-session.mjs';

const checks = [];
const check = async (name, action) => {
  try { checks.push({ name, ok: true, detail: await action() }); }
  catch (error) { checks.push({ name, ok: false, detail: error.message }); }
};
const config = readConfig();
await check('pinned-node', () => {
  if (process.version !== 'v22.23.3') throw new Error(`Expected v22.23.3, got ${process.version}`);
  return process.version;
});
await check('pinned-packages', () => {
  const expected = JSON.parse(fs.readFileSync(path.join(stackDir, 'package.json'))).dependencies;
  for (const [name, version] of Object.entries(expected)) {
    const actual = JSON.parse(fs.readFileSync(path.join(stackDir, 'node_modules', name, 'package.json'))).version;
    if (actual !== version) throw new Error(`${name}: expected ${version}, got ${actual}`);
  }
  return Object.keys(expected).length;
});
await check('sqlite-native-module', () => {
  const Database = createRequire(import.meta.url)('better-sqlite3');
  const db = new Database(':memory:');
  try { if (db.prepare('SELECT 1 AS ok').get().ok !== 1) throw new Error('SQLite query failed'); }
  finally { db.close(); }
  return 'opened, queried, closed';
});
await check('private-credential-files', () => {
  for (const name of ['workspace.json', 'node.json']) {
    const file = path.join(configDir, name);
    if (!fs.existsSync(file)) throw new Error(`Missing ${name}`);
    if (fs.statSync(file).mode & 0o077) throw new Error(`${name} must be mode 600`);
  }
  return 'owner-only';
});
await check('engine-health', async () => {
  const response = await fetch(`${config.baseUrl}/health`, { signal: AbortSignal.timeout(5000) });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.status;
});
await check('workspace-authentication', async () => {
  const secret = credentials();
  const me = new RelayCast({ apiKey: secret.apiKey, baseUrl: config.baseUrl }).as(secret.agents[config.identity].token);
  return (await me.channels.list()).map(c => c.name);
});
await check('broker-delivery', () => {
  const output = execFileSync(path.join(stackDir, '../node/bin/node'), [path.join(stackDir, 'cli.mjs'), 'agent-relay', 'node', 'status', '--state-dir', path.join(stateDir, 'broker')], { encoding: 'utf8', timeout: 10000 });
  if (!output.includes('Node delivery: CONNECTED')) throw new Error('Broker delivery is not CONNECTED; inspect node credentials and service logs.');
  return 'CONNECTED';
});
const session = currentSession();
if (process.env.CODEX_THREAD_ID) await check('existing-codex-app-server', async () => {
  await discoverCodexSocket(process.env.CODEX_THREAD_ID);
  return 'owns this loaded thread; no turn started';
});
else if (process.env.CLAUDE_CODE_SESSION_ID) await check('existing-claude-socket', () => {
  if (!process.env.CLAUDE_CODE_MESSAGING_TOKEN || !fs.existsSync(process.env.CLAUDE_CODE_MESSAGING_SOCKET || '')) throw new Error('Live socket is unavailable; run through the current Claude tool.');
  return 'present; no message injected';
});
if (process.env.CLAUDE_CODE_SESSION_ID && !process.env.CODEX_THREAD_ID) await check('claude-inbound-policy', () => {
  const paths = [path.join(os.homedir(), '.claude/settings.json'), path.join(process.cwd(), '.claude/settings.json'), path.join(process.cwd(), '.claude/settings.local.json')];
  const settings = paths.map(file => fs.existsSync(file) ? JSON.parse(fs.readFileSync(file)) : {});
  if (settings.some(s => ['hold', 'refuse'].includes(s.crossSessionInbound))) throw new Error('Claude settings hold/refuse peer messages. Inspect the named settings; do not claim the chat is live.');
  if (settings[0].permissions?.defaultMode === 'bypassPermissions' && settings[0].crossSessionInbound !== 'accept') throw new Error('Claude bypass mode holds detached peer input by default. Authorized fix: awstack authorize-claude --agent NAME, then verify actual native receipt.');
  return 'No configured hold found; actual runtime permission mode still requires a native probe.';
});
let joined;
if (session) {
  const file = path.join(configDir, 'sessions', `${session}.json`);
  if (fs.existsSync(file)) {
    joined = sessionStatus(session);
    await check('joined-listener', () => {
      if (!joined.running || joined.connected === false || (joined.connected === null && !joined.liveReceiptVerified) || joined.collision || !joined.nativeSocketPresent) throw new Error('Listener is dead, unconfirmed, disconnected, duplicated, or its native socket disappeared. Inspect awstack sessions; verify a legacy listener or reconnect inside the warmed chat.');
      return joined.legacyListener ? 'unique legacy listener; native probe acknowledged; live connection telemetry unavailable' : 'unique identity; connected listener; native socket present';
    });
  }
}
const proofFile = path.join(stateDir, 'live-proof.json');
const proof = fs.existsSync(proofFile) ? JSON.parse(fs.readFileSync(proofFile)) : null;
const liveChatProven = Boolean(session && joined?.running && proof?.sessionId === session && proof?.activeReplyId && proof?.idleProbeId);
const ready = checks.every(c => c.ok);
console.log(JSON.stringify({ readyForJoin: ready, liveChatProven, joined, checks,
  next: liveChatProven ? 'Observed active receipt and idle wake are recorded for this joined session.' : 'Join the warmed chat, prove automatic peer receipt and idle wake, then record those observed message IDs. Health and queue acceptance alone are not live-chat proof.' }, null, 2));
if (!ready) process.exitCode = 1;
