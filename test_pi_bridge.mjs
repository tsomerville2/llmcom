import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { openBridge, deliverPi } from './pi-bridge.mjs';
test('native text acceptance, authentication, session binding and shutdown', async () => {
 const received = [];
 const bridge = await openBridge('test-session', text => received.push(text));
 try {
  assert.equal(fs.statSync(bridge.door.socket).mode & 0o777, 0o600);
  await assert.rejects(deliverPi({...bridge.door,token:'wrong'},'forged'), /Unauthorized/);
  await assert.rejects(deliverPi({...bridge.door,sessionId:'other'},'stale'), /stale/);
  assert.deepEqual(received, []);
  assert.deepEqual(await deliverPi(bridge.door, 'Hello π captain'), {state:'native-queued'});
  assert.deepEqual(received, ['Hello π captain']);
 } finally { await bridge.close(); }
 assert.equal(fs.existsSync(bridge.door.socket),false);
 await assert.rejects(deliverPi(bridge.door,'late'));
});
test('a harness rejection is not reported as acceptance', async () => {
 const bridge = await openBridge('test', () => {throw new Error('Harness unavailable');});
 try { await assert.rejects(deliverPi(bridge.door,'hello'), /Harness unavailable/); }
 finally { await bridge.close(); }
});
test('extension binds shell identity, reports idle, rotates sessions and cleans up', async () => {
 const {default: extension} = await import('./pi-extension.ts');
 const handlers = {}, received = [];
 extension({on: (event, handler) => {handlers[event] = handler;}, sendUserMessage: (text, options) => received.push({text,options})}, {vendor:'omo'});
 let id = 'one';
 const ctx = { sessionManager: {getSessionId: () => id}, isIdle: () => true };
 try {
  await handlers.session_start({},ctx);
  const door = () => ({socket:process.env.LLMCOM_SOCKET,token:process.env.LLMCOM_TOKEN,sessionId:process.env.LLMCOM_SESSION_ID});
  const old = door();
  assert.equal(process.env.LLMCOM_VENDOR,'omo');
  assert.deepEqual(await deliverPi(old,'/literal'),{state:'native-queued',wasIdle:true});
  assert.equal(received[0].options.expandPromptTemplates,false);
  assert.equal(received[0].options.deliverAs,'followUp');
  id='two';
  await assert.rejects(deliverPi(old,'stale'), /Session changed/);
  await handlers.session_start({},ctx);
  assert.equal(fs.existsSync(old.socket),false);
  assert.equal(door().sessionId,'two');
 } finally {await handlers.session_shutdown();}
 assert.equal(process.env.LLMCOM_TOKEN,undefined);
});
