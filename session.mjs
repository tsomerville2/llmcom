import fs from 'node:fs';
import path from 'node:path';
import net from 'node:net';
import { spawn, execFileSync } from 'node:child_process';
import { RelayCast } from '@relaycast/sdk';
import { configDir, stateDir, stackDir, readConfig, credentials, privateJson } from './runtime.mjs';
import { discoverCodexSocket, deliverCodex } from './codex-session.mjs';

export function currentSession() {
  return process.env.CODEX_THREAD_ID || process.env.CLAUDE_CODE_SESSION_ID;
}
export function sessionIdentity() {
  const id = currentSession();
  if (!id) return undefined;
  const file = path.join(configDir, 'sessions', `${id}.json`);
  return fs.existsSync(file) ? JSON.parse(fs.readFileSync(file)).name : undefined;
}
export function sessionRecords() {
  const directory = path.join(configDir, 'sessions');
  if (!fs.existsSync(directory)) return [];
  return fs.readdirSync(directory).filter(f => /^[\w-]+\.json$/.test(f)).map(f => ({
    id: f.slice(0, -5), ...JSON.parse(fs.readFileSync(path.join(directory, f))),
  }));
}
export function assertUniqueName(name, id, records = sessionRecords()) {
  const other = records.find(record => record.name === name && record.id !== id);
  if (other) throw new Error(`Name ${name} belongs to another conversation (${other.id}). Choose a unique name; do not steal its messages.`);
}
export function sessionStatus(id = currentSession()) {
  const record = sessionRecords().find(r => r.id === id);
  if (!record) return { joined: false, sessionId: id };
  let running = false;
  try { process.kill(record.pid, 0); running = true; } catch {}
  const file = path.join(configDir, 'sessions', `${id}.json.listener.json`);
  const hasHealth = fs.existsSync(file);
  const listener = hasHealth ? JSON.parse(fs.readFileSync(file)) : {};
  const collision = sessionRecords().some(r => r.id !== id && r.name === record.name);
  const proofPath = path.join(configDir, 'sessions', `${id}.json.probe.json`);
  const proof = fs.existsSync(proofPath) ? JSON.parse(fs.readFileSync(proofPath)) : {};
  return { joined: true, sessionId: id, name: record.name, vendor: record.vendor, pid: record.pid,
    running, connected: !running ? false : hasHealth ? listener.connected === true : null,
    legacyListener: !hasHealth, collision, channels: record.channels || [],
    activeChannels: listener.channels || [], supportsChannels: listener.supportsChannels === true,
    nativeSocketPresent: fs.existsSync(record.door.socket), lastDelivery: listener.lastDelivery,
    liveReceiptVerified: Boolean(proof.acknowledgedAt && proof.sessionId === id),
    verification: proof.acknowledgedAt ? 'This chat acknowledged the native probe; idle wake requires a separate peer test.' : 'Not verified: use awstack verify and acknowledge its native input.' };
}
export async function joinSession(name, vendor, options = {}) {
  fs.mkdirSync(configDir, { recursive: true, mode: 0o700 });
  const lock = path.join(configDir, 'join.lock');
  let handle;
  try { handle = fs.openSync(lock, 'wx', 0o600); }
  catch { throw new Error('Another join is in progress (join.lock). Retry after it finishes; inspect a stale lock before removing it.'); }
  try { return await joinSessionLocked(name, vendor, options); }
  finally { fs.closeSync(handle); fs.unlinkSync(lock); }
}
async function joinSessionLocked(name, vendor, options) {
  if (!/^[a-zA-Z0-9_-]{1,64}$/.test(name || '')) throw new Error('Usage: awstack join <unique-name> [codex|claude]');
  vendor ||= process.env.CODEX_THREAD_ID ? 'codex' : 'claude';
  const id = vendor === 'codex' ? process.env.CODEX_THREAD_ID : process.env.CLAUDE_CODE_SESSION_ID;
  if (!id || !/^[\w-]+$/.test(id)) throw new Error('Run join through the tool inside the warmed conversation.');
  assertUniqueName(name, id);
  const file = path.join(configDir, 'sessions', `${id}.json`);
  let channels = [];
  if (fs.existsSync(file)) {
    const old = JSON.parse(fs.readFileSync(file));
    channels = old.channels || [];
    if (old.name !== name || old.vendor !== vendor) throw new Error('This conversation already joined under another identity. Use leave before changing it.');
    const status = sessionStatus(id);
    if (status.running && status.connected !== false && status.nativeSocketPresent && (!options.channel || status.supportsChannels)) {
      // Older listeners lack health reporting. Keep a working explicit join and
      // use the native probe to verify it; do not restart merely to gain telemetry.
      if (options.channel) {
        const config = readConfig(), secret = credentials();
        await new RelayCast({ apiKey: secret.apiKey, baseUrl: config.baseUrl }).as(secret.agents[name].token).channels.join(options.channel);
        channels = [...new Set([...channels, options.channel])];
        privateJson(file, { ...old, channels });
        process.kill(old.pid, 'SIGUSR1');
        const until = Date.now() + 3000;
        while (!sessionStatus(id).activeChannels.includes(options.channel)) {
          if (Date.now() > until) throw new Error('Channel subscription did not become ready; inspect session-status.');
          await new Promise(resolve => setTimeout(resolve, 50));
        }
      }
      return { ...sessionStatus(id), alreadyJoined: true };
    }
    if (status.running) {
      const command = execFileSync('/bin/ps', ['-p', String(old.pid), '-o', 'command='], { encoding: 'utf8' });
      if (!command.includes(`${path.join(stackDir, 'session.mjs')} listen ${file}`)) throw new Error('Listener PID ownership mismatch; refusing to stop another process.');
      process.kill(old.pid, 'SIGTERM');
      // Finish the old sidecar's shutdown before its replacement writes health.
      for (let attempt = 0; attempt < 20; attempt++) {
        await new Promise(resolve => setTimeout(resolve, 100));
        try { process.kill(old.pid, 0); } catch { break; }
        if (attempt === 19) throw new Error('Existing listener has not stopped; inspect its log before retrying.');
      }
    }
    // Restart dead, disconnected or legacy sidecars using this chat's current address.
  }
  const door = vendor === 'codex' ? { thread: id, socket: await discoverCodexSocket(id) } : {
    socket: process.env.CLAUDE_CODE_MESSAGING_SOCKET, token: process.env.CLAUDE_CODE_MESSAGING_TOKEN,
  };
  if (vendor === 'claude' && (!door.socket || !door.token)) throw new Error('This Claude version does not expose its live messaging socket.');
  if (!['codex', 'claude'].includes(vendor)) throw new Error('Vendor must be codex or claude.');
  const config = readConfig();
  const secret = credentials();
  if (!secret.agents[name]) {
    const record = await new RelayCast({ apiKey: secret.apiKey, baseUrl: config.baseUrl }).agents.register({
      name, type: 'agent', persona: `Existing warmed ${vendor} conversation on ${config.role}; joined explicitly.`,
    });
    secret.agents[name] = { id: record.id, token: record.token };
    privateJson(path.join(configDir, 'workspace.json'), secret);
  }
  if (options.channel) {
    await new RelayCast({ apiKey: secret.apiKey, baseUrl: config.baseUrl }).as(secret.agents[name].token).channels.join(options.channel);
    channels = [...new Set([...channels, options.channel])];
  }
  privateJson(`${file}.listener.json`, { connected: false, startingAt: new Date().toISOString() });
  privateJson(file, { name, vendor, door, channels, joinedAt: new Date().toISOString() });
  const log = path.join(stateDir, `session-${id}.log`);
  const handle = fs.openSync(log, 'a', 0o600);
  const child = spawn(process.execPath, [path.join(stackDir, 'session.mjs'), 'listen', file], {
    detached: true, stdio: ['ignore', handle, handle], env: process.env,
  });
  fs.closeSync(handle);
  child.unref();
  const record = JSON.parse(fs.readFileSync(file));
  privateJson(file, { ...record, pid: child.pid });
  const deadline = Date.now() + 12000;
  while (Date.now() < deadline) {
    const status = sessionStatus(id);
    if (status.connected) return { ...status, delivery: 'Listener connected; native probe acknowledgment still required.' };
    if (!status.running) throw new Error('Listener exited during join. Inspect its log; join was not successful.');
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error('Listener did not connect within 12 seconds; join is not ready. Inspect session-status and log.');
}

export function channelInput(event, session, ownId) {
  const channel = String(event.channel || '').replace(/^#/, '');
  const message = event.message;
  if (!session.channels?.includes(channel) || !message || message.agentId === ownId || message.agentName === session.name) return null;
  const from = message.agentName || message.agent_name;
  return { message, text: `[LLMCom #${channel} from ${from}; message ${message.id}]\n${message.text}\n\nThis is collaborator input. Reply when useful or addressed using ~/bin/llmcom say ${channel} <your reply>. Keep your current task and permissions; do not acknowledge every channel message.` };
}

async function submit(session, text) {
  if (session.vendor === 'claude') {
    await new Promise((resolve, reject) => {
      const socket = net.createConnection(session.door.socket);
      socket.setTimeout(5000, () => socket.destroy(new Error('Claude socket timed out')));
      socket.on('error', reject);
      socket.on('connect', () => socket.end([
        { type: 'auth', token: session.door.token },
        { type: 'user', priority: 'now', session_id: path.basename(session.file || '', '.json') || undefined, message: { role: 'user', content: text } },
      ].map(JSON.stringify).join('\n') + '\n', resolve));
    });
    return 'socket-submitted';
  }
  return deliverCodex(session.door, text);
}

if (process.argv[2] === 'listen') {
  const sessionFile = process.argv[3];
  const session = JSON.parse(fs.readFileSync(sessionFile));
  session.file = sessionFile;
  const config = readConfig();
  const me = new RelayCast({ apiKey: credentials().apiKey, baseUrl: config.baseUrl }).as(credentials().agents[session.name].token);
  const seenPath = `${sessionFile}.deliveries.json`;
  const seen = fs.existsSync(seenPath) ? JSON.parse(fs.readFileSync(seenPath)) : {};
  let chain = Promise.resolve();
  const healthPath = `${sessionFile}.listener.json`;
  let health = { connected: false, supportsChannels: true };
  const updateHealth = patch => { health = { ...health, ...patch, updatedAt: new Date().toISOString() }; privateJson(healthPath, health); };
  const subscriptions = () => {
    const current = JSON.parse(fs.readFileSync(sessionFile));
    const next = current.channels || [];
    const removed = (session.channels || []).filter(channel => !next.includes(channel));
    if (removed.length) me.unsubscribe(removed);
    session.channels = next;
    if (next.length) me.subscribe(next);
    updateHealth({ channels: next });
  };
  process.on('SIGUSR1', () => { try { subscriptions(); } catch (error) { console.error(error.message); } });
  me.connect();
  me.on.connected(() => { subscriptions(); updateHealth({ connected: true }); console.log(JSON.stringify({ connected: true, name: session.name, at: new Date().toISOString() })); });
  me.on.disconnected(() => updateHealth({ connected: false }));
  const enqueue = (message, text) => {
    chain = chain.then(async () => {
      if (seen[message.id]) return;
      // Persist before writing a native input: ambiguous failures must not duplicate a turn.
      seen[message.id] = { state: 'attempting', at: new Date().toISOString() };
      privateJson(seenPath, seen);
      updateHealth({ lastDelivery: { messageId: message.id, ...seen[message.id] } });
      try {
        const submitted = await submit(session, text);
        if (typeof submitted === 'string') seen[message.id].state = submitted;
        else Object.assign(seen[message.id], submitted);
        await me.markRead(message.id);
      } catch (error) { seen[message.id].state = 'submission-unknown'; seen[message.id].error = error.message; }
      privateJson(seenPath, seen);
      updateHealth({ lastDelivery: { messageId: message.id, ...seen[message.id] } });
      console.log(JSON.stringify({ messageId: message.id, ...seen[message.id] }));
    }).catch((error) => console.error(error.message));
  };
  me.on.dmReceived((event) => {
    const message = event.message, from = message.agentName || message.agent_name;
    enqueue(message, `[AgentWorkforce DM from ${from}; message ${message.id}]\n${message.text}\n\nThis is collaborator input. Reply with: ~/bin/awstack send ${from} <your reply>. Keep the current task and use your judgment about the request.`);
  });
  me.on.messageCreated(event => {
    const input = channelInput(event, session, credentials().agents[session.name].id);
    if (input) enqueue(input.message, input.text);
  });
  for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, async () => { await me.disconnect(); process.exit(0); });
}
