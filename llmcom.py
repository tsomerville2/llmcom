"""Friendly channels for warmed chats. Legacy awstack commands stay available."""
import argparse
import getpass
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import onboard

HOME = Path.home()
CONFIG = HOME / '.config/agentworkforce'
STACK = HOME / '.local/share/agentworkforce/stack'
NODE = STACK.parent / 'node/bin/node'

def slug(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-') or 'chat'

def channel_name(value):
    value = value.removeprefix('#').lower()
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', value):
        raise ValueError('Channel name must contain letters, numbers, hyphens or underscores.')
    return value

def chat_title(vendor, session):
    if vendor == 'claude' and session:
        for p in (HOME / '.claude/sessions').glob('*.json'):
            try:
                d = json.loads(p.read_text())
                if d.get('sessionId') == session and isinstance(d.get('name'), str): return d['name']
            except (ValueError, OSError): pass
    if vendor == 'codex' and session:
        for p in sorted((HOME / '.codex').glob('state_*.sqlite'), reverse=True):
            try:
                with sqlite3.connect(p.as_uri() + '?mode=ro', uri=True) as db:
                    row = db.execute('SELECT title FROM threads WHERE id = ?', (session,)).fetchone()
                    # Long auto-titles are usually the original prompt, not a
                    # deliberate /rename. Prefer the project name in that case.
                    if row and row[0] and len(row[0]) <= 120: return row[0]
            except sqlite3.Error: pass
    return Path.cwd().name or 'chat'

def generated_name(title, username, vendor):
    prefix = slug(username)[:20] + '-' + slug(vendor)[:12] + '-'
    # cmux commonly decorates the visible chat title with " | project".
    title = title.split(' | ',1)[0]
    return prefix + slug(title)[:64-len(prefix)].rstrip('-')

def runtime(*args):
    if not NODE.exists() or not (CONFIG / 'stack.json').exists():
        raise ValueError('This Mac is not set up. Run llmcom setup --help for the installation arguments.')
    environment = dict(os.environ)
    environment.pop('NODE_OPTIONS', None)
    return subprocess.run([str(NODE), str(STACK / 'awstack.mjs'), *args], check=True, env=environment)

def main():
    if len(sys.argv)>1 and sys.argv[1] in ('phone','--setup'):
        from connector import main as connector_main
        guided = sys.argv[1] == '--setup'
        phone=argparse.ArgumentParser(description='Prepare this Mac for phone access; --setup also joins when run inside a coding conversation.')
        phone.add_argument('channel',nargs='?',default='myphone')
        phone.add_argument('--no-open',action='store_true')
        phone.add_argument('--open',action='store_true',help='Open the optional private browser instructions.')
        phone.add_argument('--client',choices=['claude','openai'],default='claude')
        args=phone.parse_args(sys.argv[2:])
        room = channel_name(args.channel)
        connector_main(['enable','--channel',room,'--add-channels','--client',args.client]+(['--no-open'] if args.no_open or (guided and not args.open) else []))
        if guided:
            onboard.install_skill()
            inside = bool(os.environ.get('CODEX_THREAD_ID') or os.environ.get('CLAUDE_CODE_SESSION_ID'))
            if inside:
                print('Joining this coding conversation to '+room+'...', flush=True)
                subprocess.run([sys.executable,str(Path(__file__).parent/'llmcom'),'join',room],check=True)
                print('Local join command completed. Native receipt and a phone round trip still need verification.')
            else:
                print('NEXT: In your existing Claude Code or Codex chat, ask: Run llmcom join '+room+' and reply to my phone.')
            if args.client == 'claude':
                print('CLAUDE: https://claude.ai/customize/connectors')
                print('Add > Add custom connector. Name: LLMCom Remote. The private setup file above contains your URL and Authorization value. Paste the URL, Continue, choose No sign-in, add an Authorization request header, then Add.')
                print('If Request headers is missing, stop: this account screen cannot finish this connection method.')
            print('PHONE: Enable LLMCom in a new chat; ask it to join '+room+' as my-phone, say hello, then listen for replies.')
            print('AGENT: Continue setup using the installed llmcom skill (llmcom --skill). Help with the browser if available; the user handles sign-in/access approval. Keep credentials private. Verify a message in both directions before claiming success.')
            print('Optional illustrated help: https://llmcom-connector.fly.dev/setup#'+args.client)
            print('Open private instructions: llmcom phone '+room+' --client '+args.client)
        return
    if len(sys.argv)>1 and sys.argv[1]=='connector':
        from connector import main as connector_main
        connector_main(sys.argv[2:]);return
    p = argparse.ArgumentParser(description='Live text channels in your existing Claude/Codex chat; no new conversation.')
    sub = p.add_subparsers(dest='command', required=True)
    s = sub.add_parser('setup', epilog='For automatic Mac and phone setup: llmcom --setup. Agent instructions: llmcom --skill. Illustrated help: https://llmcom-connector.fly.dev/setup', help='Create a channel; install this Mac too when installation arguments are supplied.')
    s.add_argument('--local',action='store_true',help='Host a private workspace on this Mac; no SSH or imported credentials.'); s.add_argument('--workspace', default=None, help='Workspace name from the invitation; preserved on an existing installation.'); s.add_argument('channel', nargs='?', default='team'); s.add_argument('--computer'); s.add_argument('--ssh-host'); s.add_argument('--credentials-file'); s.add_argument('--port', type=int, default=8787, help='Local tunnel port.'); s.add_argument('--relay-port', type=int, help='Relay listening port on the SSH host (default 8787 for new setup).'); s.add_argument('--harness', choices=['auto','both','claude','codex','none'], default='auto'); s.add_argument('--dry-run', action='store_true'); s.add_argument('--offline',action='store_true',help='Use the bundled Apple Silicon rescue snapshot explicitly; private server access is still required.')
    j = sub.add_parser('join', help='Join a channel as this chat, using its renamed title when available.')
    j.add_argument('channel', nargs='?', default='team'); j.add_argument('--name'); j.add_argument('--title'); j.add_argument('--vendor', choices=['claude','codex']); j.add_argument('--dry-run', action='store_true'); j.add_argument('--no-config', action='store_true', help='Do not merge authorized Claude incoming/join settings.'); j.add_argument('--probe', action='store_true', help='Send another native receipt probe, even if already verified.')
    t = sub.add_parser('say', help='Post to a joined channel.'); t.add_argument('channel'); t.add_argument('text', nargs='+')
    d = sub.add_parser('send', help='Send a direct message to another chat.'); d.add_argument('peer'); d.add_argument('text', nargs='+')
    for command in ['status','doctor','sessions','leave','verify','channels']: sub.add_parser(command)
    a = sub.add_parser('ack'); a.add_argument('nonce')
    r = sub.add_parser('repair'); r.add_argument('--dry-run', action='store_true')
    info = sub.add_parser('discover', help='Show saved relay host, SSH ports and conversations without credentials.')
    info.add_argument('--check', action='store_true', help='Check SSH with existing trust and local relay health; does not send chat messages.')
    info.add_argument('--session', help='Select a local conversation by session ID; defaults to this chat when available.')
    invite = sub.add_parser('invite', help='Print credential-free instructions for a teammate to join a recorded channel.')
    invite.add_argument('channel')
    invite.add_argument('--session')
    sub.add_parser('tui', help='Choose a joined conversation and generate its invitation interactively.')
    desktop = sub.add_parser('desktop', help='Configure desktop integrations; capability limits are reported explicitly.')
    desktop.add_argument('action', choices=['install-claude','serve-events','init-events','serve-chat'])
    desktop.add_argument('--dry-run', action='store_true')
    desktop.add_argument('--accounts-file', help='Private event account configuration.')
    desktop.add_argument('--account')
    desktop.add_argument('--channel', action='append', default=[])
    desktop.add_argument('--token-file')
    desktop.add_argument('--state-file', help='Private persistent event database.')
    desktop.add_argument('--port', type=int, default=8790)
    args = p.parse_args()
    if args.command == 'desktop' and args.action == 'init-events':
        if not args.accounts_file or not args.token_file or not args.account:
            raise ValueError('init-events requires --accounts-file, --token-file, --account and --channel.')
        from event_setup import provision
        print(json.dumps(provision(args.accounts_file,args.token_file,args.account,args.channel,args.dry_run),indent=2))
        return
    if args.command == 'desktop' and args.action == 'serve-events':
        if not args.accounts_file or not args.state_file:
            raise ValueError('serve-events requires --accounts-file and --state-file; see references/desktop.md.')
        if args.dry_run:
            print(json.dumps({'writes':False,'bind':'127.0.0.1','port':args.port,'delivery':'MCP Events; authenticated HTTPS ingress and subscribed ChatGPT Work chat still required.'}))
            return
        from event_server import main as serve
        serve(['--accounts-file', args.accounts_file, '--state-file', args.state_file, '--port', str(args.port), '--relay'])
        return
    if args.command == 'desktop' and args.action == 'serve-chat':
        if not args.accounts_file or not args.state_file: raise ValueError('serve-chat requires --accounts-file and --state-file.')
        if args.dry_run:
            print(json.dumps({'writes':False,'bind':'127.0.0.1','port':args.port,'delivery':'On-demand remote MCP; public HTTPS required. No idle wake.'}));return
        from remote_chat import main as serve
        serve(['--accounts-file',args.accounts_file,'--state-file',args.state_file,'--port',str(args.port)])
        return
    if args.command == 'desktop':
        from desktop_setup import install_claude
        print(json.dumps(install_claude(HOME, Path(__file__).parent / 'desktop_mcp.py', args.dry_run), indent=2))
        return
    if args.command == 'tui':
        from tui import run
        run(CONFIG)
        return
    if args.command == 'invite':
        from discovery import discover, invitation
        print(invitation(discover(CONFIG, args.session or os.environ.get('CODEX_THREAD_ID') or os.environ.get('CLAUDE_CODE_SESSION_ID')), channel_name(args.channel)))
        return
    if args.command == 'discover':
        from discovery import discover, check_connection
        result = discover(CONFIG, args.session or os.environ.get('CODEX_THREAD_ID') or os.environ.get('CLAUDE_CODE_SESSION_ID'))
        if args.check:
            result['checks'] = check_connection(result)
            result['reachability'] = 'Checked from this computer only; see checks. Recipient access is independent.'
        print(json.dumps(result, indent=2))
        return
    if args.command == 'setup':
        channel = channel_name(args.channel)
        installed = (CONFIG / 'stack.json').exists()
        if installed:
            if args.local and __import__('connection').service_mode(HOME, json.loads((CONFIG/'stack.json').read_text())) != 'server': raise ValueError('Already configured for a remote workspace; refusing replacement.')
            existing=json.loads((CONFIG/'stack.json').read_text())
            for key,value in [('role',args.computer),('sshHost',args.ssh_host),('workspace',args.workspace),('relayPort',args.relay_port)]:
                if value is not None and value != existing.get(key, 8787 if key == 'relayPort' else None):raise ValueError('Existing '+key+' differs; refusing replacement.')
            onboard.ensure_installed_runtime(offline=args.offline,dry_run=args.dry_run)
        if not installed:
            local = args.local or (not args.ssh_host and not args.credentials_file)
            if local:
                import socket
                if args.ssh_host or args.credentials_file: raise ValueError('--local cannot be combined with remote connection arguments.')
                computer = args.computer or ('mac-' + slug(socket.gethostname().split('.')[0]))[:40].rstrip('-')
                onboard.install(argparse.Namespace(name=computer, ssh_host=None, credentials_file=None, port=args.port, relay_port=args.port, workspace=args.workspace or computer+'-local', harness=args.harness, dry_run=args.dry_run, offline=args.offline, local=True))
            elif not args.computer or not args.ssh_host or not args.credentials_file:
                print(json.dumps({'status':'needs-input','writes':False,'missing':[key for key,value in [('computer',args.computer),('sshHost',args.ssh_host),('credentialsFile',args.credentials_file)] if not value],
                                  'next':'Ask the owner for only the missing private connection arguments, then repeat llmcom setup '+channel+'. Do not invent access or credentials.'},indent=2));raise SystemExit(2)
            if not local: onboard.install(argparse.Namespace(name=args.computer, ssh_host=args.ssh_host, credentials_file=args.credentials_file, port=args.port, relay_port=args.relay_port or 8787, workspace=args.workspace or 'team', harness=args.harness, dry_run=args.dry_run, offline=args.offline))
        if args.dry_run:
            print(json.dumps({'dryRun':True, 'writes':False, 'channel':channel, 'next':'Create channel; join it from the warmed chat.'})); return
        runtime('channel-create', channel)
        print('Ready. In each warmed chat: /llmcom join ' + channel)
    elif args.command == 'join':
        channel = channel_name(args.channel)
        vendor = args.vendor or ('codex' if os.environ.get('CODEX_THREAD_ID') else 'claude')
        session = os.environ.get('CODEX_THREAD_ID') if vendor == 'codex' else os.environ.get('CLAUDE_CODE_SESSION_ID')
        config = json.loads((CONFIG / 'stack.json').read_text()) if (CONFIG / 'stack.json').exists() else {'role':'teammate'}
        record = CONFIG / 'sessions' / ((session or 'unknown') + '.json')
        existing = json.loads(record.read_text()) if record.exists() else {}
        title = args.title or chat_title(vendor, session)
        username = config.get('username') or os.environ.get('LLMCOM_USERNAME') or getpass.getuser()
        name = args.name or existing.get('name') or generated_name(title, username, vendor)
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', name): raise ValueError('Invalid chat identity; use a short name containing letters, numbers, underscores or hyphens.')
        if args.dry_run or not session:
            print(json.dumps({'writes':False, 'insideConversation':bool(session), 'channel':channel, 'chatTitle':title, 'identity':name, 'joinCommand':'~/bin/llmcom join ' + channel, 'next':'Run through the warmed chat shell; its native title/address will be detected there.'}, indent=2)); return
        if not (CONFIG/'stack.json').exists():
            print(json.dumps({'status':'needs-setup','writes':False,'next':'For your own local workspace run llmcom setup '+channel+' --local, then join again. No SSH or credential file needed. To join someone else, use their invitation setup instead.'}));raise SystemExit(2)
        if vendor == 'claude' and not args.no_config:
            # The user-invoked join explicitly asks for incoming collaborator text.
            onboard.authorize_claude(name)
        runtime('channel-join', channel, name, vendor)
        proof = record.with_name(record.name + '.probe.json')
        verified = proof.exists() and json.loads(proof.read_text()).get('acknowledgedAt')
        if args.probe or not proof.exists(): runtime('verify')
        elif not verified:print(json.dumps({'receiptPending':True,'next':'A receipt probe is already pending for this chat. Acknowledge only automatic native receipt; --probe explicitly sends another.'}))
    elif args.command == 'say': runtime('post', channel_name(args.channel), *args.text)
    elif args.command == 'send': runtime('send', args.peer, *args.text)
    elif args.command == 'status': runtime('sessions')
    elif args.command == 'repair': onboard.repair(args)
    elif args.command == 'ack': runtime('ack', args.nonce)
    else: runtime(args.command)

if __name__ == '__main__':
    try: main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print('llmcom: ' + str(error), file=sys.stderr); sys.exit(1)
