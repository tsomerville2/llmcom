// OAuth authorization-code + S256 PKCE for OpenAI clients; long-lived credentials never enter URLs.
import fs from 'node:fs';
import path from 'node:path';
import {randomBytes,createHash} from 'node:crypto';
const secret=()=>randomBytes(32).toString('base64url');
const hash=s=>createHash('sha256').update(s).digest('hex');
const challenge=s=>createHash('sha256').update(s).digest('base64url');
const scope='llmcom';
export function createOAuth({directory,origin,accountExists,limited}){
 const resource=origin+'/mcp',file=path.join(directory,'oauth.json');
 const data=fs.existsSync(file)?JSON.parse(fs.readFileSync(file,'utf8')):{clients:{},tokens:{},refresh:{}};
 const pairs=new Map(Object.entries(data.pairs||{})),requests=new Map(Object.entries(data.requests||{})),codes=new Map(Object.entries(data.codes||{}));
 function save(){data.pairs=Object.fromEntries(pairs);data.requests=Object.fromEntries(requests);data.codes=Object.fromEntries(codes);const tmp=file+'.tmp';fs.writeFileSync(tmp,JSON.stringify(data),{mode:0o600});fs.renameSync(tmp,file);}
 function clean(){for(const map of [pairs,requests,codes])for(const [k,v]of map)if(v.expires<Date.now())map.delete(k);for(const group of ['tokens','refresh'])for(const [k,v]of Object.entries(data[group]))if(v.expires<Date.now()||!accountExists(v.owner))delete data[group][k];}
 function json(res,status,value){res.writeHead(status,{'content-type':'application/json','cache-control':'no-store','x-content-type-options':'nosniff'});res.end(JSON.stringify(value));}
 function formError(req,res,status,message){
  if(!req.headers['content-type']?.startsWith('application/x-www-form-urlencoded')){json(res,status,{error:'invalid_pairing',message});return;}
  res.writeHead(status,{'content-type':'text/html; charset=utf-8','cache-control':'no-store','referrer-policy':'same-origin','content-security-policy':"default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'"});
  res.end(`<!doctype html><meta name="viewport" content="width=device-width"><title>Reconnect LLMCom</title><style>body{font:18px/1.6 system-ui;max-width:620px;margin:60px auto;padding:24px}a{color:#146953}</style><h1>Let’s reconnect LLMCom</h1><p>${message}</p><p>Return to ChatGPT, open LLMCom, and click Connect again to open a fresh sign-in page. Run <code>llmcom phone myphone --client openai</code> on your Mac for a fresh code if needed.</p><a href="/setup#openai-connect">Open the connection guide</a>`);
 }
 async function body(req){let b='';for await(const c of req){b+=c;if(Buffer.byteLength(b)>16384)throw Error('Too large');}return req.headers['content-type']?.startsWith('application/json')?JSON.parse(b):Object.fromEntries(new URLSearchParams(b));}
 function redirectOK(s){try{const u=new URL(s);return u.origin==='https://chatgpt.com'&&!u.search&&!u.hash&&(u.pathname==='/connector_platform_oauth_redirect'||/^\/connector\/oauth\/[a-zA-Z0-9_-]+$/.test(u.pathname));}catch{return false;}}
 function mint(owner,client,family=secret()){const access=secret(),refresh=secret();data.tokens[hash(access)]={owner,client,family,expires:Date.now()+3600000};data.refresh[hash(refresh)]={owner,client,family,expires:Date.now()+30*86400000};save();return {access_token:access,refresh_token:refresh,token_type:'Bearer',expires_in:3600,scope};}
 function resolve(req){const token=req.headers.authorization?.match(/^Bearer ([A-Za-z0-9_-]{43})$/)?.[1];const t=token&&data.tokens[hash(token)];return t&&t.expires>Date.now()&&accountExists(t.owner)?t.owner:null;}
 function pair(owner){clean();const active=[...pairs].filter(([,v])=>v.owner===owner);while(active.length>=5)pairs.delete(active.shift()[0]);const code=secret();pairs.set(hash(code),{owner,expires:Date.now()+600000});save();return {pairingCode:code,expires_in:600,serverUrl:resource};}
 function revoke(owner){for(const group of ['tokens','refresh'])for(const [k,v]of Object.entries(data[group]))if(v.owner===owner)delete data[group][k];for(const map of [pairs,requests,codes])for(const [k,v]of map)if(v.owner===owner)map.delete(k);save();}
 async function handle(req,res,url){
  const route=url.pathname;
  if(!route.startsWith('/oauth/')&&!route.startsWith('/.well-known/'))return false;
  clean();
  const ip=process.env.FLY_APP_NAME?req.headers['fly-client-ip']:req.socket.remoteAddress;
  if(limited('oauth:'+ip,120,60000)){json(res,429,{error:'slow_down'});return true;}
  if(req.headers.origin&&req.headers.origin!==origin){json(res,403,{error:'invalid_request'});return true;}
  if(req.method==='GET'&&route==='/.well-known/oauth-protected-resource'){
   json(res,200,{resource,authorization_servers:[origin],scopes_supported:[scope],bearer_methods_supported:['header']});return true;
  }
  if(req.method==='GET'&&route==='/.well-known/oauth-authorization-server'){
   json(res,200,{issuer:origin,authorization_endpoint:origin+'/oauth/authorize',token_endpoint:origin+'/oauth/token',registration_endpoint:origin+'/oauth/register',revocation_endpoint:origin+'/oauth/revoke',response_types_supported:['code'],grant_types_supported:['authorization_code','refresh_token'],token_endpoint_auth_methods_supported:['none'],code_challenge_methods_supported:['S256'],scopes_supported:[scope],authorization_response_iss_parameter_supported:true});return true;
  }
  if(route==='/oauth/register'&&req.method==='POST'){
   if(limited('oauth-register:'+ip,20,3600000)||Object.keys(data.clients).length>=10000){json(res,429,{error:'slow_down'});return true;}
   const b=await body(req);
   if(!Array.isArray(b.redirect_uris)||!b.redirect_uris.length||b.redirect_uris.length>5||!b.redirect_uris.every(redirectOK)||!['none',undefined].includes(b.token_endpoint_auth_method)){json(res,400,{error:'invalid_client_metadata'});return true;}
   const client_id=secret();data.clients[client_id]={redirect_uris:b.redirect_uris};save();json(res,201,{client_id,redirect_uris:b.redirect_uris,token_endpoint_auth_method:'none',grant_types:['authorization_code','refresh_token'],response_types:['code']});return true;
  }
  if(route==='/oauth/authorize'&&req.method==='GET'){
   const q=Object.fromEntries(url.searchParams),client=data.clients[q.client_id];
   if(!client||!client.redirect_uris.includes(q.redirect_uri)||q.response_type!=='code'||q.code_challenge_method!=='S256'||! /^[A-Za-z0-9_-]{43}$/.test(q.code_challenge||'')||q.resource!==resource||!q.state||q.state.length>1024||(q.scope&&q.scope!==scope)){
    json(res,400,{error:'invalid_request'});return true;
   }
   if(requests.size>=10000){json(res,429,{error:'slow_down'});return true;}
   const csrf=secret(),cookie=secret();requests.set(hash(csrf),{...q,cookie:hash(cookie),expires:Date.now()+600000});save();
   res.writeHead(200,{'content-type':'text/html; charset=utf-8','cache-control':'no-store','referrer-policy':'same-origin','x-content-type-options':'nosniff','content-security-policy':"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",'set-cookie':'llmcom_oauth_'+hash(csrf)+'='+cookie+'; Path=/oauth; Secure; HttpOnly; SameSite=Lax; Max-Age=600'});
   res.end(`<!doctype html><meta name="viewport" content="width=device-width"><title>Connect LLMCom</title><style>body{font:18px/1.5 system-ui;max-width:620px;margin:60px auto;padding:24px;background:#f6f5f0;color:#173042}input,button{font:inherit;padding:12px;box-sizing:border-box;width:100%;margin:12px 0}button{background:#146953;color:white;border:0;border-radius:8px}</style><h1>Connect LLMCom to OpenAI</h1><p>On your Mac, run <code>llmcom phone myphone --client openai</code>. Copy the one-time pairing code from the private page it opens.</p><p>This authorizes OpenAI to join, read and send messages in rooms enabled on that Mac. It does not grant shell or file access.</p><form method="post" action="/oauth/authorize"><input type="hidden" name="csrf" value="${csrf}"><label>One-time pairing code<input type="password" name="pairing_code" required autocomplete="off" maxlength="43"></label><button type="submit">Connect this Mac’s LLMCom</button></form><p>The code expires after 10 minutes and can be used once. Close this page to cancel.</p>`);return true;
  }
  if(route==='/oauth/authorize'&&req.method==='POST'){
   if(limited('oauth-pair:'+ip,20,60000)){json(res,429,{error:'slow_down'});return true;}
   const b=await body(req),key=hash(String(b.csrf||'')),r=requests.get(key);
   const cookieName='llmcom_oauth_'+key;
   const cookies=Object.fromEntries((req.headers.cookie||'').split(';').map(x=>x.trim().split('=')));
   const cookie=cookies[cookieName],pairingCode=String(b.pairing_code||'').trim();
   const p=pairs.get(hash(pairingCode));
   let reason,message;
   if(!r){reason='sign_in_missing';message='This sign-in attempt is no longer available. Start Connect again in ChatGPT; generating a code alone does not reopen a sign-in attempt.';}
   else if(!cookie||hash(cookie)!==r.cookie){reason='browser_cookie_mismatch';message='The browser did not send the cookie for this sign-in page. Open Connect and submit in the same browser, with cookies enabled.';}
   else if(!p){reason='pairing_code_missing';message='This pairing code was not recognized. It may have been used, expired, or replaced. Copy a fresh code from Terminal; the sign-in page itself is still valid.';}
   else if(!accountExists(p.owner)){reason='installation_missing';message='The Mac connection was removed. Run phone setup again on that Mac.';}
   if(reason){console.info('oauth_pair_rejected',reason);formError(req,res,400,message);return true;}
   pairs.delete(hash(pairingCode));requests.delete(key);const code=secret();codes.set(hash(code),{...r,owner:p.owner,expires:Date.now()+60000});save();
   const target=new URL(r.redirect_uri);target.searchParams.set('code',code);target.searchParams.set('state',r.state);target.searchParams.set('iss',origin);
   res.writeHead(303,{location:target.href,'cache-control':'no-store','referrer-policy':'no-referrer','set-cookie':cookieName+'=; Path=/oauth; Secure; HttpOnly; SameSite=Lax; Max-Age=0'});res.end();return true;
  }
  if(route==='/oauth/token'&&req.method==='POST'){
   const b=await body(req);let grant;
   if(b.grant_type==='authorization_code'){
    const k=hash(String(b.code||'')),r=codes.get(k);
    if(r&&r.client_id===b.client_id&&r.redirect_uri===b.redirect_uri&&b.resource===resource&&/^[A-Za-z0-9._~-]{43,128}$/.test(b.code_verifier||'')&&challenge(b.code_verifier)===r.code_challenge){codes.delete(k);grant={owner:r.owner,client:r.client_id};}
   }else if(b.grant_type==='refresh_token'){
    const k=hash(String(b.refresh_token||'')),r=data.refresh[k];
    if(r&&r.client===b.client_id&&(!b.resource||b.resource===resource)&&(!b.scope||b.scope===scope)){delete data.refresh[k];grant=r;}
   }
   if(!grant||!accountExists(grant.owner)){json(res,400,{error:'invalid_grant'});return true;}
   json(res,200,mint(grant.owner,grant.client,grant.family));return true;
  }
  if(route==='/oauth/revoke'&&req.method==='POST'){
   const b=await body(req),k=hash(String(b.token||''));const grant=data.tokens[k]||data.refresh[k];if(grant?.client===b.client_id)for(const g of ['tokens','refresh'])for(const [key,v]of Object.entries(data[g]))if(v.family===grant.family)delete data[g][key];save();json(res,200,{});return true;
  }
  json(res,404,{error:'not_found'});return true;
 }
 return {handle,resolve,pair,revoke,resource,challenge:res=>res.setHeader('WWW-Authenticate',`Bearer resource_metadata="${origin}/.well-known/oauth-protected-resource", scope="${scope}"`)};
}
