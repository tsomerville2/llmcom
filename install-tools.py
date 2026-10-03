#!/usr/bin/env python3
"""Install wrappers/config and a launchd service; npm dependencies are installed separately."""
import argparse
import json
import os
import pathlib
import plistlib
import shutil
import re
from urllib.parse import urlparse

parser = argparse.ArgumentParser()
parser.add_argument('role')
parser.add_argument('--ssh-host')
parser.add_argument('--port', type=int)
parser.add_argument('--workspace')
parser.add_argument('--no-services', action='store_true')
args = parser.parse_args()
if not re.fullmatch(r'[a-z][a-z0-9-]{0,39}', args.role):
    parser.error('role must be a short lowercase computer name')
home = pathlib.Path.home()
source = pathlib.Path(__file__).resolve().parent
root = home / '.local/share/agentworkforce'
stack = root / 'stack'
config = home / '.config/agentworkforce'
state = home / '.local/state/agentworkforce'
existing = json.loads((config / 'stack.json').read_text()) if (config / 'stack.json').exists() else {}
if existing.get('role', args.role) != args.role:
    raise SystemExit('This computer already has a different role; refusing to replace it.')
for name in ['agent-relay', 'ai-hist', 'ai-hist-mcp', 'trail', 'flows', 'relaycast-mcp', 'awstack', 'llmcom']:
    target = home / 'bin' / name
    if target.exists() and '# EXP31 AgentWorkforce wrapper' not in target.read_text():
        raise SystemExit(f'Refusing to replace unrelated executable: {target}')
port = args.port or urlparse(existing.get('baseUrl', 'http://127.0.0.1:8787')).port or 8787
if not 1024 <= port <= 65535:
    parser.error('port must be between 1024 and 65535')
ssh_host = args.ssh_host or existing.get('sshHost', 'bertha')
if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9@._:-]*', ssh_host):
    parser.error('invalid SSH destination')
for directory in [config, state, stack, home / 'bin', home / 'Library/LaunchAgents']:
    directory.mkdir(parents=True, exist_ok=True)
for directory in [config, state]:
    directory.chmod(0o700)
for name in ['package.json', 'package-lock.json', 'install-tools.py', 'runtime.mjs', 'cli.mjs', 'server.mjs', 'awstack.mjs', 'session.mjs', 'codex-session.mjs', 'doctor.mjs', 'onboard.py', 'SKILL.md', 'awstack', 'llmcom', 'llmcom.py', 'LLMCOM-SKILL.md', 'VERSION']:
    if not (source / name).exists():
        continue
    if source / name != stack / name:
        shutil.copy2(source / name, stack / name)
if (source / 'flows').exists() and source != stack:
    shutil.copytree(source / 'flows', stack / 'flows', dirs_exist_ok=True)
if (source / 'references').exists() and source != stack:
    shutil.copytree(source / 'references', stack / 'references', dirs_exist_ok=True)
settings = {**existing, 'role': args.role, 'identity': existing.get('identity', f'{args.role}-tools'),
            'baseUrl': f'http://127.0.0.1:{port}', 'sshHost': ssh_host,
            'workspace': args.workspace or existing.get('workspace', 'exp31-collaboration'), 'primaryRecall': 'navcom',
            'historySharing': 'local-only', 'cloudMirroring': False}
(config / 'stack.json').write_text(json.dumps(settings, indent=2) + '\n')
(config / 'stack.json').chmod(0o600)
for name in ['agent-relay', 'ai-hist', 'ai-hist-mcp', 'trail', 'flows', 'relaycast-mcp', 'awstack', 'llmcom']:
    target = home / 'bin' / name
    marker = '# EXP31 AgentWorkforce wrapper'
    if target.exists() and marker not in target.read_text():
        raise SystemExit(f'Refusing to replace unrelated executable: {target}')
    if name in ['awstack', 'llmcom'] and (stack / 'awstack').exists():
        shutil.copy2(stack / 'awstack', target)
        target.chmod(0o755)
        continue
    entry = stack / ('awstack.mjs' if name == 'awstack' else 'cli.mjs')
    # All paths are derived from this user's home and passed as fixed, quoted strings.
    text = f'#!/bin/sh\n{marker}\nexport PATH="{root / "node/bin"}:$HOME/bin:$PATH"\nexec "{root / "node/bin/node"}" "{entry}"'
    if name != 'awstack':
        text += f' "{name}"'
    target.write_text(text + ' "$@"\n')
    target.chmod(0o755)
if args.no_services:
    print(json.dumps({'role': args.role, 'stack': str(stack), 'services': False}))
    raise SystemExit(0)
label = f'com.exp31.agentworkforce.{"server" if args.role == "bertha" else "tunnel"}'
if args.role == 'bertha':
    command = [str(root / 'node/bin/node'), str(stack / 'server.mjs')]
else:
    command = ['/usr/bin/ssh', '-N', '-T', '-o', 'BatchMode=yes', '-o', 'ExitOnForwardFailure=yes',
               '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3',
               '-L', f'127.0.0.1:{port}:127.0.0.1:8787', ssh_host]
service = {'Label': label, 'ProgramArguments': command, 'RunAtLoad': True, 'KeepAlive': True,
           'ThrottleInterval': 10, 'WorkingDirectory': str(stack),
           'StandardOutPath': str(state / f'{args.role}-service.log'),
           'StandardErrorPath': str(state / f'{args.role}-service.err'),
           'EnvironmentVariables': {'PATH': f'{root / "node/bin"}:{home}/bin:/usr/bin:/bin:/usr/sbin:/sbin'}}
plist = home / 'Library/LaunchAgents' / f'{label}.plist'
with plist.open('wb') as handle:
    plistlib.dump(service, handle)
plist.chmod(0o600)
print(json.dumps({'role': args.role, 'stack': str(stack), 'service': str(plist)}))
broker_label = f'com.exp31.agentworkforce.{args.role}.broker'
broker_service = {
    'Label': broker_label,
    'ProgramArguments': [str(root / 'node/bin/node'), str(stack / 'cli.mjs'), 'agent-relay',
                         'node', 'up', '--no-spawn', '--broker-name', args.role,
                         '--state-dir', str(state / 'broker')],
    'RunAtLoad': True, 'KeepAlive': True, 'ThrottleInterval': 10,
    'WorkingDirectory': str(stack),
    'StandardOutPath': str(state / 'broker-service.log'),
    'StandardErrorPath': str(state / 'broker-service.err'),
    'EnvironmentVariables': service['EnvironmentVariables'],
}
broker_plist = home / 'Library/LaunchAgents' / f'{broker_label}.plist'
with broker_plist.open('wb') as handle:
    plistlib.dump(broker_service, handle)
broker_plist.chmod(0o600)
print(json.dumps({'brokerService': str(broker_plist)}))
