// A single-machine, application-specific MCP gateway. Never proxies arbitrary URLs.
import http from 'node:http';
import {randomBytes, createHash, timingSafeEqual} from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {WebSocketServer, WebSocket} from 'ws';
const hash = value => createHash('sha256').update(value).digest('hex');
const secret = () => randomBytes(32).toString('base64url');
const MAX = 262144;
export function createGateway({directory, timeout=25000, maxRegistrations=10000}={}) {
  fs.mkdirSync(directory,{recursive:true,mode:0o700});
  const file=path.join(directory,'accounts.json');
  const accounts=new Map(Object.entries(fs.existsSync(file)?JSON.parse(fs.readFileSync(file,'utf8')):{}));
  const sockets=new Map(), pending=new Map(), rates=new Map();
  function save(){
    const tmp=file+'.tmp'; const fd=fs.openSync(tmp,'w',0o600);
    try {fs.writeFileSync(fd,JSON.stringify(Object.fromEntries(accounts)));fs.fsyncSync(fd);}finally{fs.closeSync(fd);}
    fs.renameSync(tmp,file);
  }
  function authorized(req,record,kind){
    const token=req.headers.authorization?.match(/^Bearer ([A-Za-z0-9_-]{43})$/)?.[1];
    return !!(token && record && timingSafeEqual(Buffer.from(hash(token),'hex'),Buffer.from(record[kind],'hex')));
  }
  function reply(res,status,body){
    if(res.destroyed || res.writableEnded)return;
    res.writeHead(status,{'content-type':'application/json','cache-control':'no-store','x-content-type-options':'nosniff'});
    res.end(body===undefined?'':JSON.stringify(body));
  }
  function limited(key,limit,window){
    const now=Date.now();let r=rates.get(key);
    if(!r || now-r.start>=window){r={start:now,count:0};rates.set(key,r);}
    return ++r.count>limit;
  }
  async function body(req){
    let size=0;const chunks=[];
    for await(const chunk of req){size+=chunk.length;if(size>MAX)throw Error('Too large');chunks.push(chunk);}
    return JSON.parse(Buffer.concat(chunks).toString());
  }
  function finish(id,status,value){const p=pending.get(id);if(!p)return;clearTimeout(p.timer);pending.delete(id);reply(p.res,status,value);}
  const server=http.createServer(async(req,res)=>{
    try {
      const url=new URL(req.url,'http://gateway');
      // No browser origins are needed for this server-to-server connector.
      if(req.headers.origin)return reply(res,403,{error:'Browser origins are not permitted.'});
      if(url.pathname==='/health' && req.method==='GET')return reply(res,200,{ok:true,connected:sockets.size});
      if(url.pathname==='/installations' && req.method==='POST'){
        const ip=process.env.FLY_APP_NAME ? req.headers['fly-client-ip'] : req.socket.remoteAddress;
        if(limited('register:'+ip,5,3600000)||accounts.size>=maxRegistrations)return reply(res,429,{error:'Registration limit reached.'});
        const input=await body(req);if(input.version!==1)return reply(res,400,{error:'Unsupported client version.'});
        const id=randomBytes(16).toString('hex'), deviceKey=secret(), claudeKey=secret();
        accounts.set(id,{deviceHash:hash(deviceKey),claudeHash:hash(claudeKey),created:new Date().toISOString()});save();
        return reply(res,201,{id,deviceKey,claudeKey});
      }
      const match=url.pathname.match(/^\/(mcp|installations)\/([a-f0-9]{32})(\/rotate)?$/);
      if(!match)return reply(res,404,{error:'Not found.'});
      const [,kind,id,rotate]=match, account=accounts.get(id);
      if(!authorized(req,account,kind==='mcp'?'claudeHash':'deviceHash'))return reply(res,401,{error:'Invalid connector credential.'});
      if(kind==='installations'){
        if(req.method==='DELETE'&&!rotate){accounts.delete(id);save();sockets.get(id)?.close(1008,'Revoked');return reply(res,200,{disabled:true});}
        if(req.method==='POST'&&rotate){const claudeKey=secret();account.claudeHash=hash(claudeKey);save();return reply(res,200,{claudeKey});}
        if(req.method==='GET'&&!rotate)return reply(res,200,{connected:sockets.get(id)?.readyState===WebSocket.OPEN});
        return reply(res,405,{error:'Method not allowed.'});
      }
      if(rotate)return reply(res,404,{error:'Not found.'});
      if(req.method!=='POST')return reply(res,405,{error:'Use POST; this connector has no event stream.'});
      if(!req.headers['content-type']?.startsWith('application/json'))return reply(res,415,{error:'JSON required.'});
      if(limited('calls:'+id,120,60000))return reply(res,429,{error:'Request limit reached.'});
      const request=await body(req);
      if(!request || Array.isArray(request)||request.jsonrpc!=='2.0'||typeof request.method!=='string')return reply(res,400,{error:'Invalid MCP request.'});
      const socket=sockets.get(id);
      if(!socket||socket.readyState!==WebSocket.OPEN)return reply(res,503,{error:'Your LLMCom computer is offline. No message was queued.'});
      if([...pending.values()].filter(p=>p.owner===id).length>=4)return reply(res,429,{error:'Too many concurrent requests.'});
      const rid=secret();
      const timer=setTimeout(()=>finish(rid,504,{error:'Local tool timed out. A send may have completed; retry only with the same request_id.'}),timeout);
      pending.set(rid,{owner:id,socket,res,timer});
      res.once('close',()=>{const p=pending.get(rid);if(p){clearTimeout(p.timer);pending.delete(rid);}});
      socket.send(JSON.stringify({type:'request',id:rid,request}),err=>{if(err)finish(rid,503,{error:'Local connection lost; send outcome may be uncertain.'});});
    }catch{reply(res,400,{error:'Invalid or oversized request.'});}
  });
  server.requestTimeout=30000;server.headersTimeout=10000;
  const wss=new WebSocketServer({noServer:true,maxPayload:MAX,perMessageDeflate:false});
  server.on('upgrade',(req,socket,head)=>{
    const match=req.url?.match(/^\/connect\/([a-f0-9]{32})$/),id=match?.[1];
    if(req.headers.origin||!id||!authorized(req,accounts.get(id),'deviceHash')){socket.end('HTTP/1.1 401 Unauthorized\r\nConnection: close\r\n\r\n');return;}
    wss.handleUpgrade(req,socket,head,ws=>{
      sockets.get(id)?.close(1000,'Replaced');sockets.set(id,ws);ws.alive=true;
      ws.on('pong',()=>ws.alive=true);
      ws.on('message',raw=>{
        let message;try{message=JSON.parse(raw);}catch{ws.close(1008,'Invalid response');return;}
        const p=pending.get(message.id);
        if(!p || p.owner!==id || p.socket!==ws)return;
        if(message.type==='response')finish(message.id,message.response===null?202:200,message.response??undefined);
        else if(message.type==='failure')finish(message.id,502,{error:'Local tool failed. A send may have completed; reuse its request_id.'});
      });
      ws.on('error',()=>{});
      ws.on('close',()=>{
        if(sockets.get(id)===ws)sockets.delete(id);
        for(const [rid,p]of pending)if(p.socket===ws)finish(rid,503,{error:'Local connection lost; send outcome may be uncertain.'});
      });
    });
  });
  const heartbeat=setInterval(()=>{
    for(const ws of sockets.values()){if(!ws.alive){ws.terminate();continue;}ws.alive=false;ws.ping();}
    for(const [key,r]of rates)if(Date.now()-r.start>3600000)rates.delete(key);
  },20000);heartbeat.unref();
  return {server,close:async()=>{clearInterval(heartbeat);for(const ws of sockets.values())ws.terminate();for(const [id]of pending)finish(id,503,{error:'Gateway restarting.'});await new Promise(resolve=>server.close(resolve));wss.close();}};
}
if(process.argv[1] && import.meta.url===pathToFileURL(process.argv[1]).href){
  const gateway=createGateway({directory:process.env.DATA_DIR||'/data'});
  gateway.server.listen(Number(process.env.PORT||8080),'0.0.0.0',()=>console.log('LLMCom connector listening'));
  for(const signal of ['SIGTERM','SIGINT'])process.on(signal,async()=>{await gateway.close();process.exit(0);});
}
