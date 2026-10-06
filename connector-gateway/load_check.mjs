// Local bounded capacity check; these are synthetic clients, not Claude sessions.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {randomBytes,createHash} from 'node:crypto';
import {once} from 'node:events';
import {WebSocket} from 'ws';
import {createGateway} from './server.mjs';
const directory=fs.mkdtempSync(path.join(os.tmpdir(),'llmcom-load-'));
const count=Number(process.argv[2]||100), registrations={},clients=[];
for(let i=0;i<count;i++){
 const id=randomBytes(16).toString('hex'),key=randomBytes(32).toString('base64url'),hash=createHash('sha256').update(key).digest('hex');
 clients.push({id,key});registrations[id]={deviceHash:hash,claudeHash:hash};
}
fs.writeFileSync(path.join(directory,'accounts.json'),JSON.stringify(registrations));
const gateway=createGateway({directory});gateway.server.listen(0,'127.0.0.1');await once(gateway.server,'listening');
const base='http://127.0.0.1:'+gateway.server.address().port,sockets=[],latencies=[];
try{
 for(const c of clients){
  const ws=new WebSocket(base.replace('http:','ws:')+'/connect/'+c.id,{headers:{Authorization:'Bearer '+c.key}});await once(ws,'open');sockets.push(ws);
  ws.on('message',raw=>{const m=JSON.parse(raw);ws.send(JSON.stringify({type:'response',id:m.id,response:{jsonrpc:'2.0',id:m.request.id,result:{}}}));});
 }
 const rssMiB=process.memoryUsage().rss/1024/1024;
 for(const c of clients.slice(0,100)){
  const start=performance.now();const r=await fetch(base+'/mcp/'+c.id,{method:'POST',headers:{Authorization:'Bearer '+c.key,'Content-Type':'application/json'},body:JSON.stringify({jsonrpc:'2.0',id:1,method:'ping'})});
  if(r.status!==200)throw Error('Request failed '+r.status);await r.json();latencies.push(performance.now()-start);
 }
 latencies.sort((a,b)=>a-b);
 console.log(JSON.stringify({syntheticConnections:count,requests:latencies.length,combinedGatewayAndClientsRssMiB:Math.round(rssMiB),localP50ms:+latencies[Math.floor(latencies.length*.5)].toFixed(2),localP95ms:+latencies[Math.floor(latencies.length*.95)].toFixed(2)},null,2));
}finally{for(const ws of sockets)ws.terminate();await gateway.close();fs.rmSync(directory,{recursive:true,force:true});}
