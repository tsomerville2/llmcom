// Isolated transport test: no workspace, model or collaborator receives a probe.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import net from 'node:net';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

test('channel subscription delivers other members natively, filters self/unjoined, deduplicates and keeps DM delivery', async () => {
  const source = path.dirname(fileURLToPath(import.meta.url));
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'llmcom-listener-'));
  const stack = path.join(temporary, '.local/share/agentworkforce/stack');
  const config = path.join(temporary, '.config/agentworkforce');
  fs.mkdirSync(stack, { recursive:true }); fs.mkdirSync(path.join(config, 'sessions'), { recursive:true });
  for (const file of ['session.mjs','runtime.mjs','codex-session.mjs']) fs.copyFileSync(path.join(source,file),path.join(stack,file));
  const sdk = path.join(stack, 'node_modules/@relaycast/sdk'); fs.mkdirSync(sdk,{recursive:true});
  fs.writeFileSync(path.join(sdk,'package.json'), JSON.stringify({type:'module',exports:'./index.js'}));
  fs.writeFileSync(path.join(sdk,'index.js'), `
    const callbacks = {}; let joined = [];
    const client = {
      on: Object.fromEntries(['connected','disconnected','dmReceived','messageCreated'].map(key => [key, fn => { callbacks[key] = fn; }])),
      subscribe: list => { joined = list; }, unsubscribe: () => {}, markRead: async () => {}, disconnect: async () => {},
      connect: () => setTimeout(() => {
        callbacks.connected();
        const message = {id:'channel-one',agentId:'peer',agentName:'friend',text:'channel body'};
        if(joined.includes('alpha')) {
          callbacks.messageCreated({channel:'alpha',message});
          callbacks.messageCreated({channel:'alpha',message});
          callbacks.messageCreated({channel:'alpha',message:{...message,id:'own-echo',agentId:'own',agentName:'local'}});
          callbacks.messageCreated({channel:'beta',message:{...message,id:'unjoined'}});
        }
        callbacks.dmReceived({message:{id:'dm-one',agentId:'peer',agentName:'friend',text:'dm body'}});
      },20)
    };
    export class RelayCast { as() { return client; } }
  `);
  const ws = process.env.LLMCOM_TEST_WS || path.join(os.homedir(), '.local/share/agentworkforce/stack/node_modules/ws');
  fs.symlinkSync(ws,path.join(stack,'node_modules/ws'));
  fs.writeFileSync(path.join(config,'stack.json'),JSON.stringify({role:'test',baseUrl:'http://unused'}));
  fs.writeFileSync(path.join(config,'workspace.json'),JSON.stringify({apiKey:'fixture',agents:{local:{id:'own',token:'fixture'}}}));
  const socket = path.join(temporary,'native.sock'), frames = [];
  const server = net.createServer(connection => {
    let buffer = '';
    connection.on('data', raw => {
      buffer += raw;
      let index;
      while ((index = buffer.indexOf('\n')) >= 0) {
        const frame = JSON.parse(buffer.slice(0,index)); buffer = buffer.slice(index+1);
        if(frame.type === 'user') frames.push(frame);
      }
    });
  });
  let child;
  try {
    await new Promise(resolve => server.listen(socket, resolve));
    const sessionFile = path.join(config,'sessions/test-session.json');
    fs.writeFileSync(sessionFile, JSON.stringify({name:'local',vendor:'claude',channels:['alpha'],door:{socket,token:'fixture'}}));
    child = spawn(process.execPath,[path.join(stack,'session.mjs'),'listen',sessionFile],{env:{...process.env,HOME:temporary},stdio:['ignore','pipe','pipe']});
    let error = ''; child.stderr.on('data', data => { error += data; });
    const deadline = Date.now()+5000;
    while(frames.length<2 && Date.now()<deadline && child.exitCode === null) await new Promise(resolve => setTimeout(resolve,20));
    assert.equal(frames.length,2,error);
    assert.match(frames[0].message.content,/LLMCom #alpha from friend/);
    assert.match(frames[1].message.content,/AgentWorkforce DM from friend/);
    assert.ok(frames.every(frame => frame.priority === 'now' && frame.session_id === 'test-session'));
    const receipt = JSON.parse(fs.readFileSync(sessionFile+'.deliveries.json'));
    assert.deepEqual(Object.keys(receipt).sort(),['channel-one','dm-one']);
  } finally {
    if(child && child.exitCode === null) { child.kill('SIGTERM'); await new Promise(resolve => child.once('exit',resolve)); }
    await new Promise(resolve => server.close(resolve));
    fs.rmSync(temporary,{recursive:true,force:true});
  }
});
