import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { performance } from 'node:perf_hooks';
import { RelayCast } from '@relaycast/sdk';
import { readConfig, credentials, privateJson, configDir, stackDir, stateDir } from './runtime.mjs';
import { joinSession, sessionIdentity, currentSession, sessionStatus, sessionRecords } from './session.mjs';

process.once('uncaughtException', error => { console.error(`awstack: ${error.message}`); process.exit(1); });

const [command = 'status', ...args] = process.argv.slice(2);
const config = readConfig();
const secretPath = path.join(configDir, 'workspace.json');
const output = (value) => console.log(JSON.stringify(value, null, 2));

async function provision() {
  let secret;
  if (fs.existsSync(secretPath)) secret = credentials();
  else {
    const recoveryPath = path.join(configDir, 'workspace-bootstrap.json');
    if (!fs.existsSync(recoveryPath)) privateJson(recoveryPath, { idempotencyKey: crypto.randomUUID() });
    const recovery = JSON.parse(fs.readFileSync(recoveryPath, 'utf8'));
    const created = await RelayCast.createWorkspace(config.workspace, {
      baseUrl: config.baseUrl, idempotencyKey: recovery.idempotencyKey,
      metadata: { purpose: 'Private laptop/Bertha collaboration', primaryRecall: 'navcom' },
    });
    secret = { apiKey: created.apiKey, workspaceId: created.workspaceId, agents: {} };
    privateJson(secretPath, secret);
  }
  const relay = new RelayCast({ apiKey: secret.apiKey, baseUrl: config.baseUrl });
  for (const name of [config.identity]) {
    if (!secret.agents[name]) {
      const registered = await relay.agents.register({ name, type: 'system', persona: 'Operator tooling endpoint, not a thinking model session.' });
      secret.agents[name] = { id: registered.id, token: registered.token };
      privateJson(secretPath, secret);
    }
  }
  const me = relay.as(secret.agents[config.identity].token);
  const channels = await me.channels.list();
  for (const [name, topic] of [
    ['setup', 'Crawl: stack setup, smoke checks and observed limits.'],
    ['decisions', 'Decisions with rationale and links to trajectories and diaries.'],
    ['team', 'Walk: explicit questions, findings and handoffs between collaborators.'],
  ]) {
    if (!channels.some((channel) => channel.name === name)) await me.channels.create({ name, topic });
    await me.channels.join(name);
  }
  output({ workspace: config.workspace, agents: Object.keys(secret.agents), channels: ['general', 'setup', 'decisions', 'team'] });
}

function client(identity = process.env.AWSTACK_IDENTITY || sessionIdentity() || config.identity) {
  const secret = credentials();
  const record = secret.agents[identity];
  if (!record) throw new Error(`Unknown local identity: ${identity}`);
  return new RelayCast({ apiKey: secret.apiKey, baseUrl: config.baseUrl }).as(record.token);
}

async function connect(me) {
  me.connect();
  let timer;
  const connected = new Promise((resolve, reject) => {
    me.on.connected(() => { clearTimeout(timer); resolve(); });
    timer = setTimeout(() => reject(new Error('WebSocket connection timed out')), 12000);
  });
  await connected;
}

if (command === 'doctor') await import('./doctor.mjs');
else if (command === 'enroll-node') {
  const relay = new RelayCast({ apiKey: credentials().apiKey, baseUrl: config.baseUrl });
  const record = await relay.nodes.create({ name: config.role, role: 'broker', kind: 'ws', machineId: `exp31-${config.role}` });
  privateJson(path.join(configDir, 'node.json'), record);
  output({ enrolled: true, name: config.role, fields: Object.keys(record).filter(k => !/token/i.test(k)) });
}
else if (command === 'join') output(await joinSession(args[0], args[1]));
else if (command === 'channels') output((await client().channels.list()).map(c => ({ name:c.name, topic:c.topic })));
else if (command === 'channel-create' || command === 'channel-join') {
  const channel = args[0];
  if (!/^[a-z0-9][a-z0-9_-]{0,63}$/.test(channel || '')) throw new Error('Invalid channel name.');
  const me = client(config.identity);
  let record = (await me.channels.list()).find(c => c.name === channel);
  if (command === 'channel-create') {
    if (!record) record = await me.channels.create({ name:channel, topic:'Live collaboration between explicitly joined warmed chats.' });
    output({ ready:true, channel:record.name, next:`llmcom join ${record.name}` });
  } else {
    if (!record) throw new Error(`Channel ${channel} does not exist. Run llmcom setup ${channel} first.`);
    output(await joinSession(args[1], args[2], { channel }));
  }
}
else if (command === 'sessions') output(sessionRecords().map(record => sessionStatus(record.id)));
else if (command === 'verify' || command === 'ack') {
  const id = currentSession();
  const status = sessionStatus(id);
  if (!id || !status.joined || !status.running) throw new Error('Run this inside a joined warmed conversation.');
  const file = path.join(configDir, 'sessions', `${id}.json.probe.json`);
  if (command === 'ack') {
    const probe = JSON.parse(fs.readFileSync(file));
    if (probe.nonce !== args[0] || probe.sessionId !== id) throw new Error('Probe does not belong to this conversation.');
    privateJson(file, { ...probe, acknowledgedAt: new Date().toISOString() });
    output({ liveReceiptVerified: true, sessionId: id, name: status.name, messageId: probe.messageId,
      idleWakeProven: false, evidence: 'This conversation ran the native probe acknowledgment. A separate peer idle test is still needed.' });
  } else {
    const nonce = crypto.randomUUID();
    privateJson(file, { nonce, sessionId: id, sentAt: new Date().toISOString() });
    const sent = await client(config.identity).dm(status.name, `AWSTACK-NATIVE-VERIFY ${nonce}: If this appeared automatically as native input in this existing chat, run ~/bin/awstack ack ${nonce}. If you found it by reading inbox or polling, do not acknowledge it as native receipt. Then continue your current task. This is an authorized delivery test, not new permission.`);
    const latest = JSON.parse(fs.readFileSync(file));
    privateJson(file, { ...(latest.nonce === nonce ? latest : {}), nonce, sessionId: id, messageId: sent.id, sentAt: new Date().toISOString() });
    output({ verificationPending: true, messageId: sent.id, name: status.name, next: 'Let this turn finish so native queued input can wake the chat. Acknowledgment, not sending, proves receipt.' });
  }
}
else if (command === 'session-status' || command === 'leave') {
  const id = currentSession();
  if (!id) throw new Error('Run this inside the joined conversation.');
  const file = path.join(configDir, 'sessions', `${id}.json`);
  const record = JSON.parse(fs.readFileSync(file));
  let running = false;
  try { process.kill(record.pid, 0); running = true; } catch {}
  if (command === 'leave') {
    if (running) process.kill(record.pid, 'SIGTERM');
    fs.unlinkSync(file);
    output({ left: true, name: record.name });
  } else output(sessionStatus(id));
}
else if (command === 'provision') await provision();
else if (command === 'status') {
  const response = await fetch(`${config.baseUrl}/health`, { signal: AbortSignal.timeout(5000) });
  const secret = credentials();
  const me = client();
  const packages = JSON.parse(fs.readFileSync(path.join(stackDir, 'package.json'), 'utf8')).dependencies;
  output({ role: config.role, baseUrl: config.baseUrl, workspace: config.workspace,
    identity: config.identity, healthHttp: response.status, primaryRecall: 'navcom',
    cloudMirroring: false, packages, channels: (await me.channels.list()).map((c) => c.name),
    provisionedIdentities: Object.keys(secret.agents) });
}
else if (command === 'send') {
  const [to, ...words] = args;
  if (!to || !words.length) throw new Error('Usage: awstack send <agent> <text>');
  const sent = await client().dm(to, words.join(' '));
  output({ sent: true, to, id: sent.id });
}
else if (command === 'post') {
  const [channel, ...words] = args;
  if (!channel || !words.length) throw new Error('Usage: awstack post <channel> <text>');
  const sent = await client().send(channel, words.join(' '));
  output({ sent: true, channel, id: sent.id });
}
else if (command === 'inbox') output(await client().inbox());
else if (command === 'receive') {
  const name = args[0];
  if (!/^[a-zA-Z0-9_-]{1,64}$/.test(name || '')) throw new Error('Usage: awstack receive <name> [seconds, maximum 900]');
  const secret = credentials();
  if (!secret.agents[name]) {
    const record = await new RelayCast({ apiKey: secret.apiKey, baseUrl: config.baseUrl }).agents.register({ name, type: 'agent' });
    secret.agents[name] = { id: record.id, token: record.token };
    privateJson(secretPath, secret);
  }
  const me = client(name);
  const ready = connect(me);
  const seconds = Math.max(1, Math.min(900, Number(args[1] || 900)));
  let timer;
  const message = new Promise((resolve) => {
    me.on.dmReceived((event) => { clearTimeout(timer); resolve({ from: event.message.agentName, ...event.message }); });
    timer = setTimeout(() => resolve({ timeout: true }), seconds * 1000);
  });
  try { await ready; console.error(`Waiting as ${name}, maximum ${seconds}s; exits after one DM.`); output(await message); }
  finally { clearTimeout(timer); await me.disconnect(); }
}
else if (command === 'watch' || command === 'echo') {
  const me = client();
  const ready = connect(me);
  me.subscribe(['setup', 'decisions', 'team', '@self']);
  me.on.dmReceived((event) => {
    const { text } = event.message;
    const from = event.message.agentName ?? event.message.agent_name;
    output({ event: 'dm', from, text, receivedAt: new Date().toISOString() });
    if (command === 'echo' && text?.startsWith('STACK-PING:')) {
      void me.dm(from, `STACK-ACK:${text.slice('STACK-PING:'.length)}`).catch((error) => console.error(error.message));
    }
  });
  me.on.messageCreated((event) => output({ event: 'message', ...event }));
  await ready;
  output({ ready: true, identity: config.identity, mode: command });
  const seconds = Number(args[0] || 0);
  await new Promise((resolve) => {
    for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, resolve);
    if (seconds > 0) setTimeout(resolve, seconds * 1000);
  });
  await me.disconnect();
}
else if (command === 'ping') {
  const to = args[0] || (config.role === 'captain' ? 'bertha-tools' : 'captain-tools');
  const me = client();
  const ready = connect(me);
  const nonce = crypto.randomUUID();
  let timer;
  const response = new Promise((resolve, reject) => {
    me.on.dmReceived((event) => {
      if (event.message?.text === `STACK-ACK:${nonce}`) { clearTimeout(timer); resolve(event); }
    });
    timer = setTimeout(() => reject(new Error('No remote STACK-ACK within 12 seconds')), 12000);
  });
  try {
    await ready;
    const start = performance.now();
    await me.dm(to, `STACK-PING:${nonce}`);
    await response;
    const report = { verified: true, from: config.identity, to, roundTripMs: Math.round((performance.now() - start) * 10) / 10,
      measured: 'SDK DM to remote system endpoint and its automatic echo; excludes model thinking', at: new Date().toISOString() };
    fs.mkdirSync(stateDir, { recursive: true });
    privateJson(path.join(stateDir, 'last-ping.json'), report);
    output(report);
  } finally { clearTimeout(timer); await me.disconnect(); }
}
else throw new Error('Commands: status, join <name> [vendor], session-status, leave, provision, send, post, inbox, watch, echo, ping');
