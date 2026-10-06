// Outbound-only device connection. Requests run through the existing Python tools.
import fs from 'node:fs';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {WebSocket} from 'ws';
const configPath=process.argv[2], python=process.argv[3];
const dir=path.dirname(fileURLToPath(import.meta.url));
const statusPath=path.join(path.dirname(configPath),'status.json');
let stopped=false, active=null, retry=1000;
function status(connected,reason){
  const tmp=statusPath+'.tmp';
  fs.writeFileSync(tmp,JSON.stringify({connected,reason,updated:new Date().toISOString()}),{mode:0o600});fs.renameSync(tmp,statusPath);
}
function dispatch(request){return new Promise((resolve,reject)=>{
  const child=spawn(python,[path.join(dir,'connector_worker.py'),configPath],{stdio:['pipe','pipe','ignore'],env:{...process.env,NODE_OPTIONS:''}});
  let data='',settled=false;
  function finish(error,value){if(settled)return;settled=true;clearTimeout(timer);error?reject(error):resolve(value);}
  const timer=setTimeout(()=>{child.kill('SIGKILL');finish(Error('Timeout'));},23000);
  child.stdout.on('data',chunk=>{data+=chunk;if(Buffer.byteLength(data)>262144){child.kill('SIGKILL');finish(Error('Oversized reply'));}});
  child.on('error',e=>finish(e));
  child.on('close',code=>{try{if(code!==0)throw Error('Worker failed');finish(null,JSON.parse(data));}catch(e){finish(e);}});
  child.stdin.on('error',()=>{});child.stdin.end(JSON.stringify(request));
});}
function connect(){
  if(stopped)return;
  let config;
  try{config=JSON.parse(fs.readFileSync(configPath,'utf8'));}catch{status(false,'Configuration unavailable');return;}
  const url=new URL('/connect/'+config.id,config.gateway);url.protocol=url.protocol==='https:'?'wss:':'ws:';
  const ws=new WebSocket(url,{headers:{Authorization:'Bearer '+config.deviceKey},maxPayload:262144,perMessageDeflate:false,handshakeTimeout:10000});active=ws;
  let queued=0,chain=Promise.resolve(),lastPing=Date.now();
  const watchdog=setInterval(()=>{if(Date.now()-lastPing>45000)ws.terminate();},15000);
  ws.on('ping',()=>lastPing=Date.now());
  ws.on('open',()=>{retry=1000;lastPing=Date.now();status(true,'Connected');});
  ws.on('error',()=>status(false,'Gateway connection unavailable'));
  ws.on('message',raw=>{
    let message;try{message=JSON.parse(raw);}catch{ws.close(1008);return;}
    if(message.type!=='request'||typeof message.id!=='string')return;
    const received=Date.now();
    if(++queued>4){--queued;ws.send(JSON.stringify({type:'failure',id:message.id}));return;}
    chain=chain.then(async()=>{
      // Never execute a queued send after its network request has expired/disconnected.
      if(ws.readyState!==WebSocket.OPEN)return;
      if(Date.now()-received>2000){ws.send(JSON.stringify({type:'failure',id:message.id}));return;}
      try{const response=await dispatch(message.request);if(ws.readyState===WebSocket.OPEN)ws.send(JSON.stringify({type:'response',id:message.id,response}));}
      catch{if(ws.readyState===WebSocket.OPEN)ws.send(JSON.stringify({type:'failure',id:message.id}));}
    }).finally(()=>--queued);
  });
  ws.on('close',(code)=>{
    clearInterval(watchdog);status(false,code===1008?'Credential revoked':'Disconnected; reconnecting');
    if(!stopped)setTimeout(connect,retry+Math.random()*500);retry=Math.min(retry*2,30000);
  });
}
for(const signal of ['SIGTERM','SIGINT'])process.on(signal,()=>{stopped=true;active?.close();status(false,'Stopped');setTimeout(()=>process.exit(0),500);});
connect();
