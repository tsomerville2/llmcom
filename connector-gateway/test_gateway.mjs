import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {once} from 'node:events';
import {WebSocket} from 'ws';
import {createGateway} from './server.mjs';
const delay=ms=>new Promise(r=>setTimeout(r,ms));
async function fixture(t,timeout=1000){
 const directory=fs.mkdtempSync(path.join(os.tmpdir(),'llmcom-gateway-'));
 const gateway=createGateway({directory,timeout});gateway.server.listen(0,'127.0.0.1');await once(gateway.server,'listening');
 const base='http://127.0.0.1:'+gateway.server.address().port;
 t.after(async()=>{await gateway.close();fs.rmSync(directory,{recursive:true,force:true});});
 async function call(route,token,body,method='POST',headers={}){return fetch(base+route,{method,headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{}),...headers},...(body!==undefined?{body:JSON.stringify(body)}:{})});}
 const register=async()=>{const r=await call('/installations',null,{version:1});assert.equal(r.status,201);return r.json();};
 async function device(a){const ws=new WebSocket(base.replace('http:','ws:')+'/connect/'+a.id,{headers:{Authorization:'Bearer '+a.deviceKey}});await once(ws,'open');return ws;}
 return {gateway,base,call,register,device,directory};
}
const request={jsonrpc:'2.0',id:1,method:'tools/list'};
test('account isolation, offline handling, roundtrip and revoked credentials',async t=>{
 const f=await fixture(t),a=await f.register(),b=await f.register();
 assert.equal((await f.call('/mcp/'+a.id,b.claudeKey,request)).status,401);
 assert.equal((await f.call('/mcp/'+a.id,a.deviceKey,request)).status,401);
 assert.equal((await f.call('/mcp/'+a.id,a.claudeKey,request)).status,503);
 const wa=await f.device(a),wb=await f.device(b);
 const response=f.call('/mcp/'+a.id,a.claudeKey,request);const [raw]=await once(wa,'message');const packet=JSON.parse(raw);
 wb.send(JSON.stringify({type:'response',id:packet.id,response:{stolen:true}}));
 wa.send(JSON.stringify({type:'response',id:packet.id,response:{jsonrpc:'2.0',id:1,result:{tools:[]}}}));
 assert.deepEqual(await (await response).json(),{jsonrpc:'2.0',id:1,result:{tools:[]}});
 assert.equal((await f.call('/mcp/'+a.id,a.claudeKey,request,'POST',{Origin:'https://evil.example'})).status,403);
 const rotation=await (await f.call('/installations/'+a.id+'/rotate',a.deviceKey)).json();
 assert.equal((await f.call('/mcp/'+a.id,a.claudeKey,request)).status,401);
 assert.equal((await f.call('/installations/'+a.id,a.deviceKey,undefined,'DELETE')).status,200);
 assert.equal((await f.call('/mcp/'+a.id,rotation.claudeKey,request)).status,401);
 assert.ok(!fs.readFileSync(path.join(f.directory,'accounts.json'),'utf8').includes(b.deviceKey));
});
test('timeouts and disconnects are explicit; no request queued for a replacement device',async t=>{
 const f=await fixture(t,60),a=await f.register(),ws=await f.device(a);
 assert.equal((await f.call('/mcp/'+a.id,a.claudeKey,request)).status,504);
 const pending=f.call('/mcp/'+a.id,a.claudeKey,request);await once(ws,'message');ws.terminate();
 assert.equal((await pending).status,503);
 const next=await f.device(a);let delivered=0;next.on('message',()=>delivered++);await delay(80);assert.equal(delivered,0);
});
test('persistent registrations survive process restart',async t=>{
 const f=await fixture(t),a=await f.register();await f.gateway.close();
 const other=createGateway({directory:f.directory});other.server.listen(0,'127.0.0.1');await once(other.server,'listening');
 t.after(()=>other.close());
 const r=await fetch('http://127.0.0.1:'+other.server.address().port+'/installations/'+a.id,{headers:{Authorization:'Bearer '+a.deviceKey}});
 assert.equal(r.status,200);assert.deepEqual(await r.json(),{connected:false});
});
test('notification returns HTTP 202 and GET does not pretend to be SSE',async t=>{
 const f=await fixture(t),a=await f.register(),ws=await f.device(a);
 ws.on('message',raw=>ws.send(JSON.stringify({type:'response',id:JSON.parse(raw).id,response:null})));
 assert.equal((await f.call('/mcp/'+a.id,a.claudeKey,{jsonrpc:'2.0',method:'notifications/initialized'})).status,202);
 assert.equal((await f.call('/mcp/'+a.id,a.claudeKey,undefined,'GET')).status,405);
});

test('real device process and Python tools isolate two homes and deduplicate sends',async t=>{
 const {spawn}=await import('node:child_process');
 const f=await fixture(t,75000), root=path.resolve(import.meta.dirname,'..');
 async function local(a){
  const home=fs.mkdtempSync(path.join(os.tmpdir(),'llmcom-device-'));t.after(()=>fs.rmSync(home,{recursive:true,force:true}));
  const stack=path.join(home,'.local/share/agentworkforce/stack'), conf=path.join(home,'.config/agentworkforce/connector');
  fs.mkdirSync(stack,{recursive:true});fs.mkdirSync(conf,{recursive:true});fs.mkdirSync(path.join(stack,'../node/bin'),{recursive:true});
  fs.symlinkSync(process.execPath,path.join(stack,'../node/bin/node'));
  for(const name of fs.readdirSync(root).filter(n=>n.endsWith('.py')||n==='connector_client.mjs'))fs.copyFileSync(path.join(root,name),path.join(stack,name));
  fs.symlinkSync(path.join(import.meta.dirname,'node_modules'),path.join(stack,'node_modules'));
  fs.writeFileSync(path.join(conf,'../stack.json'),JSON.stringify({identity:'fixture'}));
  fs.writeFileSync(path.join(stack,'awstack.mjs'),`import fs from 'node:fs';const file=new URL('./messages.json',import.meta.url);const m=fs.existsSync(file)?JSON.parse(fs.readFileSync(file)):[];if(process.argv[2]==='post'){const item={id:String(m.length+1),text:process.argv[4]};m.push(item);fs.writeFileSync(file,JSON.stringify(m));console.log(JSON.stringify({id:item.id,sent:true}));}else console.log(JSON.stringify(m.slice().reverse()));`);
  const config=path.join(conf,'config.json');fs.writeFileSync(config,JSON.stringify({...a,gateway:f.base,channels:['room']}),{mode:0o600});
  const child=spawn(process.execPath,[path.join(stack,'connector_client.mjs'),config,process.env.PYTHON||'/usr/bin/python3'],{env:{...process.env,HOME:home},stdio:'ignore'});
  t.after(async()=>{child.kill('SIGTERM');if(child.exitCode===null)await once(child,'exit');});
  for(let i=0;i<50;i++){const r=await f.call('/installations/'+a.id,a.deviceKey,undefined,'GET');if((await r.json()).connected)break;await delay(30);}
  return {home,stack};
 }
 const a=await f.register(),b=await f.register();const la=await local(a);await local(b);
 const tool=async(account,name,args)=>{
  const r=await f.call('/mcp/'+account.id,account.claudeKey,{jsonrpc:'2.0',id:1,method:'tools/call',params:{name,arguments:args}});
  assert.equal(r.status,200);return r.json();
 };
 const join=await tool(a,'llmcom_join',{channel:'room',name:'test'}),cid=JSON.parse(join.result.content[0].text).conversation_id;
 assert.ok((await tool(b,'llmcom_read',{channel:'room',conversation_id:cid})).error);
 assert.ok((await tool(a,'llmcom_join',{channel:'secret',name:'test'})).error);
 const args={channel:'room',conversation_id:cid,text:'only once',request_id:'retry-proof',wait_for_reply:false};
 assert.deepEqual(await tool(a,'llmcom_say',args),await tool(a,'llmcom_say',args));
 assert.equal(JSON.parse(fs.readFileSync(path.join(la.stack,'messages.json'))).length,1);
 const read=await tool(a,'llmcom_read',{channel:'room',conversation_id:cid});assert.equal(JSON.parse(read.result.content[0].text).messages.length,0);
 const startedWait=Date.now();
 const waiting=tool(a,'llmcom_say',{channel:'room',conversation_id:cid,text:'question',request_id:'auto-wait-proof'});
 const messagesFile=path.join(la.stack,'messages.json');
 for(let i=0;i<50;i++){if(JSON.parse(fs.readFileSync(messagesFile)).length===2)break;await delay(30);}
 await delay(20500);
 const messages=JSON.parse(fs.readFileSync(messagesFile));assert.equal(messages.length,2);messages.push({id:'3',text:'peer response',agentName:'test-peer'});fs.writeFileSync(messagesFile,JSON.stringify(messages));
 const answer=JSON.parse((await waiting).result.content[0].text);assert.equal(answer.wait_status,'messages');assert.ok(Date.now()-startedWait>18000);assert.ok(Date.now()-startedWait<60000);assert.deepEqual(answer.messages.map(m=>m.text),['peer response']);
});

test('public setup guide is available without opening browser access to private routes',async t=>{
 const f=await fixture(t);
 for(const route of ['/', '/setup']){
  const r=await fetch(f.base+route);assert.equal(r.status,200);assert.match(r.headers.get('content-type'),/text\/html/);
  const text=await r.text();assert.match(text,/llmcom phone myphone/);assert.match(text,/60 seconds/);assert.doesNotMatch(text,/rk_live_/);
 }
 const install=await fetch(f.base+'/install.sh');assert.equal(install.status,200);assert.match(await install.text(),/llmcom>=0.4.7/);
 const blocked=await f.call('/installations',null,{version:1},'POST',{Origin:'https://evil.example'});assert.equal(blocked.status,403);
});
