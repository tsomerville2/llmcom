import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {once} from 'node:events';
import {createHash,randomBytes} from 'node:crypto';
import {WebSocket} from 'ws';
import {createGateway} from './server.mjs';
const origin='https://llmcom.example',resource=origin+'/mcp';
const redirect='https://chatgpt.com/connector_platform_oauth_redirect';
async function fixture(t){
 const directory=fs.mkdtempSync(path.join(os.tmpdir(),'llmcom-oauth-'));
 let gateway,base;
 async function start(){gateway=createGateway({directory,origin});gateway.server.listen(0,'127.0.0.1');await once(gateway.server,'listening');base='http://127.0.0.1:'+gateway.server.address().port;}
 await start();t.after(async()=>{await gateway.close();fs.rmSync(directory,{recursive:true,force:true});});
 const call=(route,body,headers={},method='POST')=>fetch(base+route,{method,redirect:'manual',headers:{'content-type':'application/json',...headers},...(body===undefined?{}:{body:JSON.stringify(body)})});
 const bearer=token=>({authorization:'Bearer '+token});
 const account=async()=>{const r=await call('/installations',{version:1});assert.equal(r.status,201);return r.json();};
 const client=async()=>{const r=await call('/oauth/register',{redirect_uris:[redirect],token_endpoint_auth_method:'none'});assert.equal(r.status,201);return (await r.json()).client_id;};
 async function authorize(a,c,overrides={}){
  const pair=await (await call('/installations/'+a.id+'/pair',{},bearer(a.deviceKey))).json();
  const verifier=randomBytes(32).toString('base64url');
  const query={client_id:c,redirect_uri:redirect,response_type:'code',scope:'llmcom',state:'state-test',resource,code_challenge_method:'S256',code_challenge:createHash('sha256').update(verifier).digest('base64url'),...overrides};
  const r=await call('/oauth/authorize?'+new URLSearchParams(query),undefined,{},'GET');
  if(r.status!==200)return {r};
  const html=await r.text(),csrf=html.match(/name="csrf" value="([^"]+)"/)[1],cookie=r.headers.get('set-cookie').split(';')[0];
  assert.equal(r.headers.get('referrer-policy'),'same-origin');
  const submit=(headers={cookie,origin},code=pair.pairingCode)=>call('/oauth/authorize',{csrf,pairing_code:code},headers);
  const submitForm=()=>fetch(base+'/oauth/authorize',{method:'POST',redirect:'manual',headers:{cookie,origin,'content-type':'application/x-www-form-urlencoded'},body:new URLSearchParams({csrf,pairing_code:pair.pairingCode})});
  return {r,pair,verifier,submit,submitForm,cookie};
 }
 async function grant(a,c){const flow=await authorize(a,c);const r=await flow.submit();assert.equal(r.status,303);const target=new URL(r.headers.get('location'));assert.equal(target.origin,'https://chatgpt.com');assert.equal(target.searchParams.get('state'),'state-test');assert.equal(target.searchParams.get('iss'),origin);return {flow,body:{grant_type:'authorization_code',client_id:c,redirect_uri:redirect,resource,code:target.searchParams.get('code'),code_verifier:flow.verifier}};}
 return {call,bearer,account,client,authorize,grant,directory,restart:async()=>{await gateway.close();await start();},device:async a=>{const ws=new WebSocket(base.replace('http:','ws:')+'/connect/'+a.id,{headers:bearer(a.deviceKey)});await once(ws,'open');return ws;}};
}
test('OAuth discovery, registered redirects, resource binding, CSRF, PKCE and replay protection',async t=>{
 const f=await fixture(t),a=await f.account(),c=await f.client();
 let r=await f.call('/mcp',{});assert.equal(r.status,401);assert.match(r.headers.get('www-authenticate'),/oauth-protected-resource/);
 const metadata=await (await f.call('/.well-known/oauth-protected-resource',undefined,{},'GET')).json();assert.equal(metadata.resource,resource);
 for(const uri of ['https://evil.example/','https://chatgpt.com.evil.example/connector_platform_oauth_redirect',redirect+'?evil=1','http://chatgpt.com/connector_platform_oauth_redirect'])assert.equal((await f.call('/oauth/register',{redirect_uris:[uri]})).status,400);
 for(const override of [{resource:'https://evil.example/mcp'},{redirect_uri:'https://evil.example'},{code_challenge_method:'plain'},{scope:'admin'}])assert.equal((await f.authorize(a,c,override)).r.status,400);
 const flow=await f.authorize(a,c);assert.equal((await flow.submit({})).status,400);assert.equal((await flow.submit({cookie:'llmcom_oauth='+'x'.repeat(43)})).status,400);
 assert.equal((await flow.submit({cookie:'x',origin:'https://evil.example'})).status,403);
 assert.equal((await flow.submit({cookie:'x',origin:'null'})).status,403);
 const first=await flow.submitForm();assert.equal(first.status,303);const duplicate=await flow.submit();assert.equal(duplicate.status,200);assert.match(await duplicate.text(),/already submitted/);
 const code=new URL(first.headers.get('location')).searchParams.get('code');
 const body={grant_type:'authorization_code',client_id:c,redirect_uri:redirect,resource,code,code_verifier:flow.verifier};
 for(const change of [{code_verifier:'z'.repeat(43)},{resource:'https://evil.example'},{client_id:'wrong'},{redirect_uri:redirect+'/wrong'}])assert.equal((await f.call('/oauth/token',{...body,...change})).status,400);
 const token=await (await f.call('/oauth/token',body)).json();assert.ok(token.access_token);assert.equal((await f.call('/oauth/token',body)).status,400);
 assert.equal((await f.call('/mcp',{},f.bearer(token.access_token))).status,400);
 const stored=fs.readFileSync(path.join(f.directory,'oauth.json'),'utf8');for(const secret of [token.access_token,token.refresh_token,flow.pair.pairingCode,code])assert.ok(!stored.includes(secret));
 assert.equal(fs.statSync(path.join(f.directory,'oauth.json')).mode&0o777,0o600);
});
test('two independently paired accounts route separately, survive restart, refresh and revoke',async t=>{
 const f=await fixture(t),a=await f.account(),b=await f.account(),c=await f.client(),otherClient=await f.client();
 const ga=await f.grant(a,c),gb=await f.grant(b,c);
 const ta=await (await f.call('/oauth/token',ga.body)).json(),tb=await (await f.call('/oauth/token',gb.body)).json();
 await f.restart();
 const wa=await f.device(a),wb=await f.device(b);
 for(const [ws,owner]of [[wa,'a'],[wb,'b']])ws.on('message',raw=>{const m=JSON.parse(raw);ws.send(JSON.stringify({type:'response',id:m.id,response:{jsonrpc:'2.0',id:m.request.id,result:{owner}}}));});
 const request={jsonrpc:'2.0',id:1,method:'tools/list'};
 for(const [token,owner]of [[ta,'a'],[tb,'b']])assert.equal((await (await f.call('/mcp',request,f.bearer(token.access_token))).json()).result.owner,owner);
 assert.equal((await f.call('/mcp/'+b.id,request,f.bearer(ta.access_token))).status,401);
 const refresh={grant_type:'refresh_token',client_id:c,refresh_token:ta.refresh_token,resource};
 assert.equal((await f.call('/oauth/token',{...refresh,client_id:otherClient})).status,400);
 assert.equal((await f.call('/oauth/token',{...refresh,resource:'https://evil.example'})).status,400);
 const next=await (await f.call('/oauth/token',refresh)).json();assert.ok(next.access_token);assert.equal((await f.call('/oauth/token',refresh)).status,400);
 await f.call('/installations/'+a.id+'/oauth',undefined,f.bearer(a.deviceKey),'DELETE');
 for(const token of [ta.access_token,next.access_token])assert.equal((await f.call('/mcp',request,f.bearer(token))).status,401);
 assert.equal((await f.call('/oauth/token',{...refresh,refresh_token:next.refresh_token})).status,400);
 assert.equal((await f.call('/mcp',request,f.bearer(tb.access_token))).status,200);
 assert.equal((await f.call('/mcp/'+a.id,request,f.bearer(a.claudeKey))).status,200);
 await f.call('/installations/'+b.id,undefined,f.bearer(b.deviceKey),'DELETE');assert.equal((await f.call('/mcp',request,f.bearer(tb.access_token))).status,401);
});
test('token revocation removes its grant family; expired tokens cannot reconnect',async t=>{
 const f=await fixture(t),a=await f.account(),c=await f.client(),g=await f.grant(a,c);
 const token=await (await f.call('/oauth/token',g.body)).json();
 const refresh={grant_type:'refresh_token',client_id:c,refresh_token:token.refresh_token,resource};
 const next=await (await f.call('/oauth/token',refresh)).json();
 await f.call('/oauth/revoke',{client_id:c,token:next.refresh_token});
 for(const access of [token.access_token,next.access_token])assert.equal((await f.call('/mcp',{},f.bearer(access))).status,401);
 assert.equal((await f.call('/oauth/token',{...refresh,refresh_token:next.refresh_token})).status,400);
 const g2=await f.grant(a,c),expired=await (await f.call('/oauth/token',g2.body)).json();
 const file=path.join(f.directory,'oauth.json'),stored=JSON.parse(fs.readFileSync(file));
 for(const group of ['tokens','refresh'])for(const value of Object.values(stored[group]))value.expires=Date.now()-1000;
 fs.writeFileSync(file,JSON.stringify(stored));await f.restart();
 assert.equal((await f.call('/mcp',{},f.bearer(expired.access_token))).status,401);
 assert.equal((await f.call('/oauth/token',{...refresh,refresh_token:expired.refresh_token})).status,400);
});

test('pending pairing survives restart, new codes and parallel browser tabs',async t=>{
 const f=await fixture(t),a=await f.account(),c=await f.client();
 const first=await f.authorize(a,c),second=await f.authorize(a,c);
 await f.restart();
 // Both codes and both CSRF/cookie bindings remain valid after redeployment.
 assert.equal((await first.submit({cookie:first.cookie+'; '+second.cookie,origin})).status,303);
 assert.equal((await second.submitForm()).status,303);
 const repeated=await first.submitForm();assert.equal(repeated.status,200);assert.match(await repeated.text(),/already submitted/);
});

test('pairing lifetime stays ten minutes and pending secrets are stored hashed',async t=>{
 const f=await fixture(t),a=await f.account(),c=await f.client(),flow=await f.authorize(a,c);
 const stored=fs.readFileSync(path.join(f.directory,'oauth.json'),'utf8');
 assert.ok(!stored.includes(flow.pair.pairingCode));
 assert.ok(!stored.includes(flow.cookie.split('=')[1]));
 const original=Date.now;
 try{Date.now=()=>original()+600001;assert.equal((await flow.submitForm()).status,400);}
 finally{Date.now=original;}
});
