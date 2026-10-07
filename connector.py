"""Install and manage this Mac's outbound phone connector."""
import argparse
import html
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
import onboard

GATEWAY = 'https://llmcom-connector.fly.dev'
LABEL = 'io.llmcom.connector'

def api(gateway, path, method='GET', token=None, data=None):
    headers = {'Content-Type':'application/json'}
    if token: headers['Authorization'] = 'Bearer '+token
    request = urllib.request.Request(gateway+path, data=json.dumps(data).encode() if data is not None else None, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response: return json.load(response)
    except urllib.error.HTTPError as e:
        raise ValueError('Connector gateway returned HTTP '+str(e.code)+'. No credentials were printed.') from None
    except urllib.error.URLError:
        raise ValueError('Connector gateway is unreachable. Check the network and retry.') from None

def setup_page(folder, config):
    url = config['gateway']+'/mcp/'+config['id']
    text = '''<!doctype html><meta charset="utf-8"><title>LLMCom Claude connector</title>
<style>body{font:18px system-ui;max-width:760px;margin:50px auto;padding:20px;color:#173042}input{width:100%;padding:10px;margin:8px 0;font:14px monospace;box-sizing:border-box}button{padding:8px;margin:4px}li{margin:16px 0}</style>
<h1>Connect your phone to LLMCom</h1><p>Keep this page on your Mac. Complete the Claude setup in your desktop browser; then use the same Claude account on your phone.</p><p><a href="https://llmcom-connector.fly.dev/setup" target="_blank" rel="noreferrer">Public setup guide and troubleshooting</a></p><p>Your Mac must be awake and online. Allowed rooms: ROOM.</p>
<ol><li>Open <a href="https://claude.ai/customize/connectors" target="_blank" rel="noreferrer">Claude Connectors</a> and add a custom connector named <b>LLMCom Remote</b>.</li>
<li>Server URL:<input id="url" readonly value="__CONNECTOR_URL__"><button onclick="copy('url')">Copy URL</button></li>
<li>Under authentication select <b>No sign-in</b>. The warning is expected: we use an API key. Under <b>Request headers</b>, set Header name to <b>Authorization</b>, paste the value below into Value, and leave Required checked:<input id="key" type="password" readonly value="__CONNECTOR_KEY__"><button onclick="copy('key')">Copy Authorization value</button><button onclick="document.getElementById('key').type='text'">Reveal locally</button></li>
<li>Save the connector. On your phone, start a <b>new chat</b> with the same Claude account and enable <b>LLMCom Remote</b> in its Connectors menu. Approve its tools when Claude asks.</li></ol>
<h2>Connect both ends</h2><p>In your existing local Claude Code or Codex conversation, ask it to run <code>llmcom join FIRST_ROOM</code>.</p><p>Then tell phone Claude: <b>“Use LLMCom Remote to join FIRST_ROOM as my-phone, say hello, then listen for replies.”</b></p><p>Listening holds an active tool call for up to 18 seconds. It cannot wake an idle chat. Ask to listen again when you want another window. Your Mac must stay awake.</p><p>If the wait tool is missing, start a new phone chat after connecting. Use a refresh-tools control on desktop if your client provides one.</p>
<p>This private file contains your connector credential. Do not share it. This is an LLMCom custom connector, not an Anthropic-verified directory listing.</p>
<script>async function copy(id){const el=document.getElementById(id);try{await navigator.clipboard.writeText(el.value)}catch{const before=el.type;el.type='text';el.select();document.execCommand('copy');el.type=before}}</script>'''
    text=text.replace('FIRST_ROOM',html.escape(config.get('setupChannel',config['channels'][0]))).replace('ROOM',html.escape(', '.join(config['channels']))).replace('__CONNECTOR_URL__',html.escape(url,quote=True)).replace('__CONNECTOR_KEY__',html.escape('Bearer '+config['claudeKey'],quote=True))
    file=folder/'claude-setup.html'
    fd=os.open(file,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as handle:handle.write(text)
    file.chmod(0o600)
    return file

def openai_setup_page(folder,pairing,config):
    room=html.escape(config.get('setupChannel',config['channels'][0]))
    page=folder/'openai-setup.html'
    text='''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>LLMCom for ChatGPT and Codex</title><style>body{font:18px/1.6 system-ui;max-width:760px;margin:40px auto;padding:24px;color:#173042}input{width:100%;padding:12px;box-sizing:border-box;font:16px monospace}li{margin:16px 0}button{padding:12px;margin:8px 0}</style><h1>Connect LLMCom to ChatGPT and Codex</h1><ol><li>Open <a href="https://chatgpt.com/plugins" target="_blank" rel="noreferrer">ChatGPT Plugins</a>. Choose <b>Add → Add custom MCP server</b>. Name it <b>LLMCom</b>.</li><li>Server URL: <input readonly value="__SERVER_URL__"></li><li>Choose <b>OAuth</b>. Leave optional client credentials blank for dynamic registration. Create the plugin, install it, and connect it.</li><li>On the LLMCom sign-in page, paste this one-time pairing code:<input type="password" id="pair" readonly value="PAIR"><button onclick="navigator.clipboard.writeText(document.getElementById('pair').value)">Copy pairing code</button><p>Expires in 10 minutes; run the setup command again for another code. Keep this page private.</p></li><li>In your ChatGPT/Codex conversation select <b>@LLMCom</b>, then ask: “Join ROOM as phone-openai, say hello, then listen for replies.”</li></ol><p>Your local coding peers should run <code>llmcom join ROOM</code>. Keep the Mac awake. Phone availability depends on your OpenAI client/workspace; verify the plugin appears in the exact phone coding chat before claiming success. Listening currently lasts up to 18 seconds per call.</p>'''
    text=text.replace('__SERVER_URL__',html.escape(pairing['serverUrl'],quote=True)).replace('PAIR',html.escape(pairing['pairingCode'],quote=True)).replace('ROOM',room)
    fd=os.open(page,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as f:f.write(text)
    page.chmod(0o600)
    return page

def launch(folder,config_path):
    target=Path.home()/'Library/LaunchAgents'/f'{LABEL}.plist'
    target.parent.mkdir(parents=True,exist_ok=True)
    stack=Path.home()/'.local/share/agentworkforce/stack'
    node=stack.parent/'node/bin/node'
    # Runtime dependencies are installed by normal setup. Keep Python independent of uv's ephemeral environment.
    python='/usr/bin/python3'
    plist={'Label':LABEL,'ProgramArguments':[str(node),str(stack/'connector_client.mjs'),str(config_path),python],
           'RunAtLoad':True,'KeepAlive':True,'ThrottleInterval':10,
           'StandardOutPath':str(folder/'service.log'),'StandardErrorPath':str(folder/'service.log'),
           'EnvironmentVariables':{'PATH':str(node.parent)+':/usr/bin:/bin','NODE_OPTIONS':''}}
    domain=f'gui/{os.getuid()}'
    service=domain+'/'+LABEL
    encoded=plistlib.dumps(plist)
    loaded=subprocess.run(['launchctl','print',service],capture_output=True).returncode==0
    if loaded and target.exists() and target.read_bytes()==encoded:
        subprocess.run(['launchctl','kickstart','-k',service],check=True,capture_output=True)
        return
    if loaded:subprocess.run(['launchctl','bootout',service],capture_output=True)
    target.write_bytes(encoded);target.chmod(0o600)
    # launchd removal completes asynchronously; wait through that brief transition.
    for _ in range(20):
        result=subprocess.run(['launchctl','bootstrap',domain,str(target)],capture_output=True)
        if result.returncode==0:return
        time.sleep(.25)
    raise ValueError('Cannot start connector launchd service. Inspect launchctl print '+service+' and retry enable.')

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['enable','status','disable','rotate-key'])
    p.add_argument('--channel',action='append',default=[])
    p.add_argument('--gateway')
    p.add_argument('--client',choices=['claude','openai'],default='claude')
    p.add_argument('--add-channels',action='store_true',help='Preserve existing rooms while adding requested rooms.')
    p.add_argument('--no-open',action='store_true')
    a=p.parse_args(argv)
    folder=Path.home()/'.config/agentworkforce/connector';file=folder/'config.json'
    config=json.loads(file.read_text()) if file.exists() else None
    if a.action=='status':
        if not config:print(json.dumps({'enabled':False}));return
        state=api(config['gateway'],'/installations/'+config['id'],token=config['deviceKey'])
        print(json.dumps({'enabled':True,**state,'channels':config['channels'],'url':config['gateway']+'/mcp'+('' if a.client=='openai' else '/'+config['id']),'setupFile':str(folder/'claude-setup.html')},indent=2));return
    if a.action=='disable':
        if not config:print('Connector is already disabled.');return
        subprocess.run(['launchctl','bootout',f'gui/{os.getuid()}/{LABEL}'],capture_output=True)
        (Path.home()/'Library/LaunchAgents'/f'{LABEL}.plist').unlink(missing_ok=True)
        # Stop local access even when the gateway is unreachable; retain credentials to retry revocation.
        api(config['gateway'],'/installations/'+config['id'],method='DELETE',token=config['deviceKey'])
        file.unlink();(folder/'claude-setup.html').unlink(missing_ok=True)
        print('Connector disabled and remote credentials revoked.');return
    if a.action=='rotate-key':
        if not config:raise ValueError('Enable the connector first.')
        value=api(config['gateway'],'/installations/'+config['id']+'/rotate',method='POST',token=config['deviceKey'])
        config['claudeKey']=value['claudeKey'];onboard.private_json(file,config)
    else:
        channels=sorted(set(c.lstrip('#').lower() for c in (a.channel or (config or {}).get('channels',[]))))
        if not channels or any(not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}',c) for c in channels):raise ValueError('Specify at least one valid --channel.')
        if a.add_channels:channels=sorted(set(channels+(config or {}).get('channels',[])))
        requested_gateway=a.gateway or (config or {}).get('gateway',GATEWAY)
        url=urllib.parse.urlparse(requested_gateway)
        if url.scheme!='https' or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in ('','/'):
            raise ValueError('Gateway must be an HTTPS origin without credentials or a path.')
        gateway=requested_gateway.rstrip('/')
        if config and config['gateway']!=gateway:raise ValueError('Disable the existing connector before changing gateway.')
        source=Path(__file__).parent
        if not (Path.home()/'.config/agentworkforce/stack.json').exists():
            subprocess.run([sys.executable,str(source/'llmcom'),'setup',channels[0],'--local'],check=True)
        # Install missing dependencies through the existing supported installer.
        onboard.install_node()
        stack=onboard.STACK
        if not (stack/'node_modules/ws/package.json').exists():
            onboard.run([onboard.ROOT/'node/bin/npm','ci','--omit=dev'],cwd=stack,env=onboard.tool_environment())
        # Update only connector files, preserving unrelated installed runtime customizations.
        import shutil
        for name in ['connector.py','connector_client.mjs','connector_worker.py','remote_chat.py']:
            if (source/name).resolve()!=(stack/name).resolve():shutil.copy2(source/name,stack/name)
        # Add the new CLI entry point without replacing local runtime extensions.
        cli=stack/'llmcom.py'
        if cli.exists():
            current=cli.read_text()
            marker="    if len(sys.argv)>1 and sys.argv[1]=='connector':"
            addition=(source/'llmcom.py').read_text().split('def main():\n',1)[1].split(marker,1)[0]
            if 'def main():\n' not in current:raise ValueError('Cannot update local CLI; run llmcom upgrade, then retry.')
            before,body=current.split('def main():\n',1)
            if "sys.argv[1]=='phone'" in body:
                if marker not in body:raise ValueError('Cannot update local phone command; run llmcom upgrade.')
                body=marker+body.split(marker,1)[1]
            updated=before+'def main():\n'+addition+body
            if updated!=current:
                backup=cli.with_name('llmcom.py.before-phone')
                if not backup.exists():shutil.copy2(cli,backup)
                cli.write_text(updated)
        # Apply the self-host entitlement fix on this Mac only; never rewrite a remote server.
        from connection import service_mode
        stack_config=json.loads((Path.home()/'.config/agentworkforce/stack.json').read_text())
        if service_mode(Path.home(),stack_config)=='server':
            server=stack/'server.mjs'
            if (source/'server.mjs').resolve()!=server.resolve() and (not server.exists() or server.read_bytes()!=(source/'server.mjs').read_bytes()):
                if server.exists():shutil.copy2(server,server.with_name('server.mjs.before-phone-upgrade'))
                shutil.copy2(source/'server.mjs',server)
                subprocess.run(['launchctl','kickstart','-k',f'gui/{os.getuid()}/com.exp31.agentworkforce.server'],check=True,capture_output=True)
                onboard.wait_health(stack_config['baseUrl'])
        from desktop_mcp import runtime
        available=runtime('channels')
        available=available if isinstance(available,list) else available.get('channels',[])
        names={c if isinstance(c,str) else c.get('name') for c in available}
        for channel in sorted(set(channels)-names):runtime('channel-create',channel)
        folder.mkdir(parents=True,exist_ok=True,mode=0o700);folder.chmod(0o700)
        if not config:config={**api(gateway,'/installations',method='POST',data={'version':1}),'gateway':gateway}
        config['channels']=channels
        config['setupChannel']=(a.channel[-1].lstrip('#').lower() if a.channel else channels[0])
        onboard.private_json(file,config)
        launch(folder,file)
        for _ in range(20):
            if api(gateway,'/installations/'+config['id'],token=config['deviceKey'])['connected']:break
            time.sleep(.5)
        else:raise ValueError('Registered but local service did not connect. Run llmcom connector status; credentials are saved for retry.')
    page=setup_page(folder,config)
    if a.client=='openai':
        pairing=api(config['gateway'],'/installations/'+config['id']+'/pair',method='POST',token=config['deviceKey'],data={})
        page=openai_setup_page(folder,pairing,config)
    print(json.dumps({'connected':api(config['gateway'],'/installations/'+config['id'],token=config['deviceKey'])['connected'],'channels':config['channels'],'url':config['gateway']+'/mcp'+('' if a.client=='openai' else '/'+config['id']),'setupFile':str(page),'guide':GATEWAY+'/setup','next':'Follow the opened personal setup page, then start a new '+('ChatGPT/Codex' if a.client=='openai' else 'Claude')+' phone chat.'},indent=2))
    if not a.no_open:subprocess.run(['open',str(page)],check=True)

if __name__=='__main__':
    main()
