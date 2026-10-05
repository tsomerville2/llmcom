// Stream only configured channels. stdout is private JSONL for the event worker.
import fs from 'node:fs';
import readline from 'node:readline';
import { RelayCast } from '@relaycast/sdk';
import { readConfig, credentials } from './runtime.mjs';
const config = readConfig();
const secret = credentials();
const identity = secret.agents?.[config.identity];
if (!identity) throw new Error('Configured relay identity is missing. Run llmcom doctor.');
const me = new RelayCast({ apiKey: secret.apiKey, baseUrl: config.baseUrl }).as(identity.token);
me.connect();
let channels = [];
const input = readline.createInterface({ input: process.stdin });
let updates = Promise.resolve();
input.on('line', line => {
 updates = updates.then(async () => {
  try {
    const next = JSON.parse(line);
    if (!Array.isArray(next) || next.some(c => typeof c !== 'string' || !/^[a-z0-9][a-z0-9_-]{0,63}$/.test(c))) return;
    const removed = channels.filter(c => !next.includes(c));
    if (removed.length) me.unsubscribe(removed);
    for (const channel of next) await me.channels.join(channel);
    channels = next;
    if (channels.length) me.subscribe(channels);
    console.log(JSON.stringify({status:'subscribed',channels}));
  } catch { console.error('Subscription update failed.'); }
 });
});
me.on.connected(() => { if (channels.length) me.subscribe(channels); console.log(JSON.stringify({status:'connected'})); });
me.on.messageCreated(event => {
  const channel = String(event.channel || '').replace(/^#/, '');
  const message = event.message;
  if (!channels.includes(channel) || !message || message.agentId === identity.id) return;
  console.log(JSON.stringify({ channel, message_id: String(message.id),
    sender: message.agentName || message.agent_name || String(message.agentId),
    text: message.text, timestamp: message.createdAt || message.created_at || new Date().toISOString() }));
});
for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, async () => { await me.disconnect(); process.exit(0); });
input.on('close', async () => { await me.disconnect(); process.exit(0); });
