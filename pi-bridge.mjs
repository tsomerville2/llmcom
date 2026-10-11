// Native pi/omo transport. Only authenticated text can enter a bound conversation.
import fs from 'node:fs';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
const LIMIT = 256 * 1024;
export async function openBridge(sessionId, receive) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'llmcom-'));
  fs.chmodSync(directory, 0o700);
  const door = { socket: path.join(directory, 'in.sock'), token: crypto.randomBytes(32).toString('hex'), sessionId };
  const clients = new Set();
  const server = net.createServer(socket => {
    socket.setEncoding('utf8');
    clients.add(socket); socket.on('close', () => clients.delete(socket));
    socket.on('error', () => {});
    socket.setTimeout(5000, () => socket.destroy());
    let buffer = '', bytes = 0, handled = false;
    socket.on('data', async chunk => {
      if (handled) return;
      bytes += Buffer.byteLength(chunk);
      if (bytes > LIMIT) { handled = true; socket.destroy(); return; }
      buffer += chunk.toString('utf8');
      if (!buffer.includes('\n')) return;
      handled = true;
      try {
        const request = JSON.parse(buffer.slice(0, buffer.indexOf('\n')));
        if (request.token !== door.token || request.sessionId !== sessionId) throw new Error('Unauthorized or stale session');
        if (typeof request.text !== 'string' || !request.text.trim()) throw new Error('Nonempty text required');
        const receipt = await receive(request.text);
        socket.end(JSON.stringify({ accepted: true, state: 'native-queued', ...(receipt?.wasIdle === undefined ? {} : {wasIdle: receipt.wasIdle}) }) + '\n');
      } catch (error) { socket.end(JSON.stringify({ accepted: false, error: error.message }) + '\n'); }
    });
  });
  try {
    await new Promise((resolve, reject) => { server.once('error', reject); server.listen(door.socket, resolve); });
    fs.chmodSync(door.socket, 0o600);
  } catch (error) { fs.rmSync(directory, { recursive: true, force: true }); throw error; }
  return { door, close: async () => {
    for (const socket of clients) socket.destroy();
    await new Promise(resolve => server.close(resolve));
    fs.rmSync(directory, { recursive: true, force: true });
  } };
}
export function deliverPi(door, text) {
  return new Promise((resolve, reject) => {
    const socket = net.createConnection(door.socket);
    socket.setEncoding('utf8');
    socket.setTimeout(5000, () => socket.destroy(new Error('pi/omo native delivery timed out')));
    let buffer = '', settled = false;
    socket.on('error', reject);
    socket.on('connect', () => socket.write(JSON.stringify({ ...door, text }) + '\n'));
    socket.on('data', chunk => {
      buffer += chunk;
      if (buffer.length > LIMIT) return socket.destroy(new Error('Oversized native response'));
      if (!buffer.includes('\n')) return;
      try {
        const result = JSON.parse(buffer.slice(0, buffer.indexOf('\n')));
        settled = true;
        if (result.accepted !== true) reject(new Error(result.error || 'Native input rejected'));
        else resolve({ state: 'native-queued', ...(result.wasIdle === undefined ? {} : {wasIdle: result.wasIdle}) });
      } catch (error) { reject(error); }
      socket.destroy();
    });
    socket.on('close', () => { if (!settled) reject(new Error('Native connection closed without acceptance')); });
  });
}
