import fs from 'node:fs';
import path from 'node:path';
import WebSocket from 'ws';

async function connection(socket) {
  const ws = new WebSocket(`ws+unix://${socket}:/`);
  const pending = new Map();
  let nextId = 0;
  ws.on('message', (raw) => {
    const message = JSON.parse(raw.toString());
    const item = pending.get(message.id);
    if (!item) return;
    pending.delete(message.id);
    clearTimeout(item.timer);
    if (message.error) item.reject(new Error(`Codex RPC ${message.error.code}: ${message.error.message}`));
    else item.resolve(message.result);
  });
  const fail = (error) => {
    for (const item of pending.values()) { clearTimeout(item.timer); item.reject(error); }
    pending.clear();
  };
  ws.on('error', fail);
  ws.on('close', () => fail(new Error('Codex app-server connection closed')));
  const request = (method, params) => new Promise((resolve, reject) => {
    const id = ++nextId;
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(`Codex RPC timed out: ${method}`)); ws.terminate(); }, 10000);
    pending.set(id, { resolve, reject, timer });
    ws.send(JSON.stringify({ id, method, params }));
  });
  const close = () => ws.close();
  try {
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => { ws.terminate(); reject(new Error('Codex socket connection timed out')); }, 5000);
      ws.once('open', () => { clearTimeout(timer); resolve(); });
      ws.once('error', (error) => { clearTimeout(timer); reject(error); });
    });
    await request('initialize', { clientInfo: { name: 'exp31_agentworkforce', version: '1' }, capabilities: { experimentalApi: true } });
    ws.send(JSON.stringify({ method: 'initialized' }));
    return { request, close };
  } catch (error) { ws.terminate(); throw error; }
}

export async function discoverCodexSocket(thread) {
  const directory = `/private/tmp/codex-daemon-${process.getuid()}`;
  const candidates = process.env.AWSTACK_CODEX_SOCKET ? [process.env.AWSTACK_CODEX_SOCKET] :
    (fs.existsSync(directory) ? fs.readdirSync(directory).map(name => path.join(directory, name)).filter(file => fs.statSync(file).isSocket()) : []);
  for (const socket of candidates) {
    let rpc;
    try {
      rpc = await connection(socket);
      const result = await rpc.request('thread/read', { threadId: thread, includeTurns: false });
      if (['active', 'idle', 'systemError'].includes(result.thread.status?.type)) return socket;
    } catch { /* Only select a server that already owns the loaded conversation. */ }
    finally { rpc?.close(); }
  }
  throw new Error('No running Codex app server owns this loaded thread. Set AWSTACK_CODEX_SOCKET to its Unix socket; no new thread will be started.');
}

export async function deliverCodex(door, text) {
  const socket = door.socket || await discoverCodexSocket(door.thread);
  const rpc = await connection(socket);
  try {
    const result = await rpc.request('turn/start', { threadId: door.thread, input: [{ type: 'text', text }] });
    return { state: 'turn-accepted', turnId: result.turn.id, turnStatus: result.turn.status };
  } finally { rpc.close(); }
}
