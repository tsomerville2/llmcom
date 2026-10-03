"""Friendly channels for warmed chats. Legacy awstack commands stay available."""
import argparse
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

def generated_name(title, computer, session):
    suffix = '-' + slug(computer)[:16] + '-' + (session[:8] if session else 'current')
    return slug(title)[:64-len(suffix)].rstrip('-') + suffix

def runtime(*args):
    if not NODE.exists() or not (CONFIG / 'stack.json').exists():
        raise ValueError('This Mac is not set up. Run llmcom setup --help for the installation arguments.')
    return subprocess.run([str(NODE), str(STACK / 'awstack.mjs'), *args], check=True)

def main():
    p = argparse.ArgumentParser(description='Live text channels in your existing Claude/Codex chat; no new conversation.')
    sub = p.add_subparsers(dest='command', required=True)
    s = sub.add_parser('setup', help='Create a channel; install this Mac too when installation arguments are supplied.')
    s.add_argument('channel', nargs='?', default='team'); s.add_argument('--computer'); s.add_argument('--ssh-host'); s.add_argument('--credentials-file'); s.add_argument('--port', type=int, default=8787); s.add_argument('--harness', choices=['auto','both','claude','codex','none'], default='auto'); s.add_argument('--dry-run', action='store_true')
    j = sub.add_parser('join', help='Join a channel as this chat, using its renamed title when available.')
    j.add_argument('channel', nargs='?', default='team'); j.add_argument('--name'); j.add_argument('--title'); j.add_argument('--vendor', choices=['claude','codex']); j.add_argument('--dry-run', action='store_true'); j.add_argument('--no-config', action='store_true', help='Do not merge authorized Claude incoming/join settings.'); j.add_argument('--probe', action='store_true', help='Send another native receipt probe, even if already verified.')
    t = sub.add_parser('say', help='Post to a joined channel.'); t.add_argument('channel'); t.add_argument('text', nargs='+')
    d = sub.add_parser('send', help='Send a direct message to another chat.'); d.add_argument('peer'); d.add_argument('text', nargs='+')
    for command in ['status','doctor','sessions','leave','verify','channels']: sub.add_parser(command)
    a = sub.add_parser('ack'); a.add_argument('nonce')
    r = sub.add_parser('repair'); r.add_argument('--dry-run', action='store_true')
    args = p.parse_args()
    if args.command == 'setup':
        channel = channel_name(args.channel)
        installed = (CONFIG / 'stack.json').exists() and NODE.exists()
        if not installed:
            if not args.computer or not args.ssh_host or not args.credentials_file:
                raise ValueError('New Mac needs --computer NAME --ssh-host HOST --credentials-file PRIVATE_FILE. These establish private access; no account or SSH key is invented.')
            onboard.install(argparse.Namespace(name=args.computer, ssh_host=args.ssh_host, credentials_file=args.credentials_file, port=args.port, workspace='exp31-collaboration', harness=args.harness, dry_run=args.dry_run))
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
        name = args.name or existing.get('name') or generated_name(title, config['role'], session)
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', name): raise ValueError('Invalid chat identity; use a short name containing letters, numbers, underscores or hyphens.')
        if args.dry_run or not session:
            print(json.dumps({'writes':False, 'insideConversation':bool(session), 'channel':channel, 'chatTitle':title, 'identity':name, 'joinCommand':'~/bin/llmcom join ' + channel, 'next':'Run through the warmed chat shell; its native title/address will be detected there.'}, indent=2)); return
        if vendor == 'claude' and not args.no_config:
            # The user-invoked join explicitly asks for incoming collaborator text.
            onboard.authorize_claude(name)
        runtime('channel-join', channel, name, vendor)
        proof = record.with_name(record.name + '.probe.json')
        verified = proof.exists() and json.loads(proof.read_text()).get('acknowledgedAt')
        if args.probe or not verified: runtime('verify')
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
