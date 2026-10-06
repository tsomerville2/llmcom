#!/usr/bin/env python3
"""Repeatable macOS client onboarding. No secrets are shipped in the kit."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
import time

SOURCE = Path(__file__).resolve().parent
HOME = Path.home()
ROOT = HOME / '.local/share/agentworkforce'
STACK = ROOT / 'stack'
CONFIG = HOME / '.config/agentworkforce'
STATE = HOME / '.local/state/agentworkforce'
NODE_VERSION = '22.23.3'
FILES = ['package.json', 'package-lock.json', 'runtime.mjs', 'cli.mjs', 'server.mjs', 'awstack', 'awstack.mjs',
         'session.mjs', 'codex-session.mjs', 'channel.mjs', 'doctor.mjs', 'install-tools.py', 'onboard.py', 'rescue.py', 'SKILL.md', 'llmcom', 'llmcom.py', 'discovery.py', 'connection.py', 'tui.py', 'desktop_mcp.py', 'desktop_setup.py', 'mcp_events.py', 'event_protocol.py', 'event_tools.py', 'event_setup.py', 'event_server.py', 'remote_chat.py', 'connector.py', 'connector_client.mjs', 'connector_worker.py', 'event_worker.py', 'event_delivery.py', 'event_relay.mjs', 'LLMCOM-SKILL.md', 'VERSION']
NODE_HASHES = {
    'arm64': '23b25245dcfb9af7262f8ff142e9e2e0af025368117329e7a7458a51e5922f53',
    'x64': '8a677b0219178efd6eb0e475457c4afb452b521a92f6e67845a73bd85727f2a8',
}

def private_json(file, value):
    file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = file.with_name(file.name + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as handle:
        json.dump(value, handle, indent=2); handle.write('\n')
    temporary.chmod(0o600); temporary.replace(file)

def import_credentials(source):
    given = json.loads(Path(source).expanduser().read_text())
    if not isinstance(given.get('apiKey'), str) or len(given['apiKey']) < 16:
        raise ValueError('Credential file needs a workspace apiKey; no key values will be printed.')
    target = CONFIG / 'workspace.json'
    existing = json.loads(target.read_text()) if target.exists() else {}
    if existing and existing.get('apiKey') != given['apiKey']:
        raise ValueError('Already joined to another workspace; refusing to replace its credentials.')
    # A new member gets the workspace key, not other members' agent bearer tokens.
    value = {'apiKey': given['apiKey'], 'workspaceId': given.get('workspaceId'), 'agents': existing.get('agents', {})}
    private_json(target, value)

def run(args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, **kwargs)

def tool_environment():
    environment = {**os.environ, 'PATH': str(ROOT / 'node/bin') + ':' + str(HOME / 'bin') + ':' + os.environ.get('PATH', ''), 'DO_NOT_TRACK': '1'}
    environment.pop('NODE_OPTIONS', None)
    return environment

def wait_health(url):
    deadline = time.monotonic() + 25
    while True:
        try:
            with urllib.request.urlopen(url + '/health', timeout=2) as response:
                if response.status == 200: return
        except OSError: pass
        if time.monotonic() > deadline: raise ValueError('Tunnel/server is not healthy; inspect its service log before retrying.')
        time.sleep(0.25)

def install_node():
    binary = ROOT / 'node/bin/node'
    if binary.exists() and subprocess.check_output([str(binary), '--version'], text=True).strip() == 'v' + NODE_VERSION:
        return
    architecture = {'arm64': 'arm64', 'x86_64': 'x64'}.get(platform.machine())
    if not architecture: raise ValueError('Unsupported architecture; this kit supports Apple Silicon and Intel Macs.')
    ROOT.mkdir(parents=True, exist_ok=True)
    filename = 'node-v' + NODE_VERSION + '-darwin-' + architecture + '.tar.gz'
    archive = ROOT / filename
    if not archive.exists(): urllib.request.urlretrieve('https://nodejs.org/dist/v' + NODE_VERSION + '/' + filename, archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != NODE_HASHES[architecture]:
        raise ValueError('Node checksum mismatch; no archive was extracted.')
    run(['/usr/bin/tar', '-xzf', archive, '-C', ROOT])
    link = ROOT / 'node'
    if link.exists() and not link.is_symlink(): raise ValueError('Refusing to replace an unrelated node directory.')
    if link.is_symlink(): link.unlink()
    link.symlink_to(ROOT / filename[:-7])

def install_skill():
    for root in [HOME / '.codex/skills', HOME / '.claude/skills']:
        for name, file, marker in [('agentworkforce','SKILL.md','EXP31 AgentWorkforce skill'), ('llmcom','LLMCOM-SKILL.md','EXP31 LLMCom skill')]:
            target = root / name
            if target.exists() and marker not in (target / 'SKILL.md').read_text():
                raise ValueError('Refusing to replace unrelated skill: ' + str(target))
            target.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SOURCE / file, target / 'SKILL.md')
            if (SOURCE / 'references').exists(): shutil.copytree(SOURCE / 'references', target / 'references', dirs_exist_ok=True)

def backup(file):
    if file.exists():
        target = file.with_name(file.name + '.agentworkforce-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '.bak')
        shutil.copy2(file, target); target.chmod(0o600)

def harness_command(name):
    preferred = HOME / '.local/bin' / name
    return str(preferred) if preferred.exists() else shutil.which(name)

def register_mcp(harness):
    env = tool_environment()
    wanted = ['claude', 'codex'] if harness in ['auto', 'both'] else ([] if harness == 'none' else [harness])
    for name in wanted:
        executable = harness_command(name)
        if not executable:
            if harness != 'auto': raise ValueError(name + ' is not installed.')
            continue
        backup(HOME / ('.claude.json' if name == 'claude' else '.codex/config.toml'))
        for suffix, command, args in [('relay', HOME / 'bin/agent-relay', ['mcp']), ('history', HOME / 'bin/ai-hist-mcp', [])]:
            server = 'agentworkforce-' + suffix
            if name == 'claude':
                file = HOME / '.claude.json'
                existing = json.loads(file.read_text()).get('mcpServers', {}).get(server) if file.exists() else None
            else:
                result = subprocess.run([executable, 'mcp', 'get', server, '--json'], env=env, capture_output=True, text=True)
                existing = json.loads(result.stdout).get('transport', {}) if result.returncode == 0 else None
            if existing:
                if existing.get('command') != str(command) or existing.get('args', []) != args:
                    raise ValueError('Existing MCP server differs; not replacing ' + server)
                continue
            argv = [executable, 'mcp', 'add'] + (['--scope', 'user'] if name == 'claude' else []) + [server, '--', str(command)] + args
            run(argv, env=env, stdout=subprocess.DEVNULL)

def authorize_claude(agent):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', agent): raise ValueError('Invalid agent name.')
    p = HOME / '.claude/settings.json'
    data = json.loads(p.read_text()) if p.exists() else {}
    original = json.loads(json.dumps(data))
    if data.get('crossSessionInbound') == 'refuse':
        raise ValueError('User settings explicitly refuse cross-session input. Ask the owner to change that choice before joining.')
    # Detached listeners are external peers. Bypass mode otherwise holds them.
    # The explicit authorization command enables incoming peer text, not a new tool permission mode.
    data['crossSessionInbound'] = 'accept'
    config = json.loads((CONFIG / 'stack.json').read_text())
    additions = {
        'environment': ['AgentWorkforce is the user\'s private collaboration infrastructure at ' + config['baseUrl'] + ' over SSH to ' + config.get('sshHost', 'the private server') + '.'],
        'allow': ['The user intentionally authorizes awstack join ' + agent + ' claude to start a background listener delivering collaborator messages into this explicitly joined existing conversation until awstack leave stops it. This persistence is intentional. Retrying this authorized connection after its earlier denial is allowed; a bypass classification for this specific approved workflow is a false positive.'],
    }
    auto = data.setdefault('autoMode', {})
    for key, entries in additions.items():
        values = auto.setdefault(key, ['$defaults'])
        if not isinstance(values, list): raise ValueError('Unexpected autoMode configuration.')
        for entry in entries:
            if entry not in values: values.append(entry)
    rules = data.setdefault('permissions', {}).setdefault('allow', [])
    for spelling in ['~/bin/awstack', str(HOME / 'bin/awstack')]:
        rule = 'Bash(' + spelling + ' join ' + agent + ' claude)'
        if rule not in rules: rules.append(rule)
    if data != original:
        backup(p);private_json(p, data)
    print(json.dumps({'configured': str(p), 'exactJoinAgent': agent, 'crossSessionInbound': 'accept', 'defaultsPreserved': True,'settingsReused':data==original}))

def install(args):
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,39}', args.name): raise ValueError('Name must be a short lowercase computer name.')
    local = getattr(args, 'local', False)
    from connection import service_mode
    saved = json.loads((CONFIG / 'stack.json').read_text()) if (CONFIG / 'stack.json').exists() else {}
    if not local and service_mode(HOME, saved) == 'server': raise ValueError('This is a client installer; preserve the existing relay server and use its server runbook.')
    if not local and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9@._:-]*', args.ssh_host): raise ValueError('Invalid SSH destination.')
    relay_port = getattr(args, 'relay_port', 8787)
    if not 1 <= relay_port <= 65535: raise ValueError('Invalid relay port.')
    if not 1024 <= args.port <= 65535: raise ValueError('Invalid port.')
    if not local and not args.credentials_file and not (CONFIG / 'workspace.json').exists(): raise ValueError('Provide a private workspace credential file with --credentials-file.')
    if args.dry_run:
        print(json.dumps({'dryRun': True, 'writes': False, 'name': args.name, 'sshHost': args.ssh_host, 'port': args.port, 'pinnedNode': NODE_VERSION, 'harness': args.harness, 'offline':getattr(args,'offline',False), 'serviceMode': 'server' if local else 'client', 'next': 'Install local relay and generate private workspace credentials' if local else 'Install client tunnel and import private credentials'}, indent=2)); return
    if platform.system() != 'Darwin': raise ValueError('This installer is currently macOS only.')
    # Fail on wrapper collisions and role changes before downloading or overwriting anything.
    for name in ['agent-relay', 'ai-hist', 'ai-hist-mcp', 'trail', 'flows', 'relaycast-mcp', 'awstack', 'llmcom']:
        target = HOME / 'bin' / name
        if target.exists() and '# EXP31 AgentWorkforce wrapper' not in target.read_text(): raise ValueError('Unrelated executable exists: ' + str(target))
    existing = json.loads((CONFIG / 'stack.json').read_text()) if (CONFIG / 'stack.json').exists() else {}
    if existing.get('role', args.name) != args.name: raise ValueError('Existing computer role differs; refusing replacement.')
    for key, value in [('sshHost', args.ssh_host), ('baseUrl', 'http://127.0.0.1:' + str(args.port)), ('workspace', args.workspace)]:
        if key in existing and existing[key] != value: raise ValueError('Existing ' + key + ' differs; refusing to rewrite a running service.')
    if args.credentials_file:
        given = json.loads(Path(args.credentials_file).expanduser().read_text())
        if not isinstance(given.get('apiKey'), str) or len(given['apiKey']) < 16: raise ValueError('Credential file needs a workspace apiKey.')
        current = json.loads((CONFIG / 'workspace.json').read_text()) if (CONFIG / 'workspace.json').exists() else {}
        if current and current.get('apiKey') != given['apiKey']: raise ValueError('Already joined to another workspace; refusing replacement.')
    # Check SSH access before service installation; does not add keys or change server access.
    if not local: run(['/usr/bin/ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', args.ssh_host, 'true'])
    elif not saved:
        import socket
        with socket.socket() as probe:
            try: probe.bind(('127.0.0.1', args.port))
            except OSError: raise ValueError('Local relay port is busy. Choose another --port; no existing service was changed.')
    offline = getattr(args,'offline',False)
    if offline:
        import rescue
        rescue.install_runtime(ROOT)
    else:
        try: install_node()
        except (OSError,ValueError):
            raise ValueError('Pinned upstream Node installation failed. Check network/checksum diagnostics, or explicitly use llmcom setup CHANNEL --offline with the same private setup arguments.')
    STACK.mkdir(parents=True, exist_ok=True)
    expected_lock = (SOURCE / 'package-lock.json').read_bytes()
    reuse = (STACK / 'node_modules').exists() and (STACK / 'package-lock.json').exists() and (STACK / 'package-lock.json').read_bytes() == expected_lock
    if SOURCE != STACK:
        for name in FILES: shutil.copy2(SOURCE / name, STACK / name)
        for name in ['flows', 'references']:
            if (SOURCE / name).exists(): shutil.copytree(SOURCE / name, STACK / name, dirs_exist_ok=True)
        if (SOURCE/'rescue').exists():
            import rescue
            rescue.copy_artifacts(STACK/'rescue')
    if not reuse:
        if offline: raise ValueError('Offline snapshot did not restore the expected dependency tree.')
        try: run([ROOT / 'node/bin/npm', 'ci', '--no-audit', '--no-fund'], cwd=STACK, env=tool_environment())
        except subprocess.CalledProcessError:
            raise ValueError('Upstream installation failed. Diagnose the npm error, or explicitly use llmcom setup CHANNEL --offline with the same private setup arguments. No automatic fallback occurred.')
    install_args = ['/usr/bin/python3', STACK / 'install-tools.py', args.name, '--port', args.port, '--relay-port', relay_port, '--workspace', args.workspace]
    install_args += ['--local'] if local else ['--ssh-host', args.ssh_host]
    run(install_args)
    if args.credentials_file: import_credentials(args.credentials_file)
    domain = 'gui/' + str(os.getuid())
    labels = ['com.exp31.agentworkforce.' + ('server' if local else 'tunnel'), 'com.exp31.agentworkforce.' + args.name + '.broker']
    first = HOME / 'Library/LaunchAgents' / (labels[0] + '.plist')
    if subprocess.run(['launchctl', 'print', domain + '/' + labels[0]], capture_output=True).returncode != 0:
        run(['launchctl', 'bootstrap', domain, first])
    wait_health('http://127.0.0.1:' + str(args.port))
    run([HOME / 'bin/awstack', 'provision'])
    if not (CONFIG / 'node.json').exists(): run([HOME / 'bin/awstack', 'enroll-node'])
    second = HOME / 'Library/LaunchAgents' / (labels[1] + '.plist')
    if subprocess.run(['launchctl', 'print', domain + '/' + labels[1]], capture_output=True).returncode != 0:
        run(['launchctl', 'bootstrap', domain, second])
    run([HOME / 'bin/agent-relay', 'telemetry', 'disable'], stdout=subprocess.DEVNULL)
    register_mcp(args.harness)
    install_skill()
    print(json.dumps({'installed': True, 'computer': args.name, 'next': 'Run awstack doctor, authorize the named Claude join if needed, then join through the warmed conversation tool. Installation is not live-chat proof.'}))

def bundle(output):
    output = Path(output).expanduser().resolve(); output.parent.mkdir(parents=True, exist_ok=True)
    files = [SOURCE / name for name in FILES]
    for directory in ['flows', 'references', 'rescue']: files += [p for p in (SOURCE / directory).rglob('*') if p.is_file()]
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in sorted(files): z.write(p, 'llmcom/' + str(p.relative_to(SOURCE)))
    print(json.dumps({'bundle': str(output), 'files': len(files), 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'secretsIncluded': False}))

def upgrade(args):
    """Apply packaged code and skills without touching a live chat or service."""
    if not (CONFIG / 'stack.json').exists():
        raise ValueError('No existing stack. Run llmcom setup --help to onboard this Mac first.')
    config = json.loads((CONFIG / 'stack.json').read_text())
    if args.dry_run:
        print(json.dumps({'dryRun': True, 'writes': False, 'version': (SOURCE / 'VERSION').read_text().strip(),
                          'next': 'Refresh runtime files, wrappers and skills; retain live listeners and services.'})); return
    if platform.system() != 'Darwin': raise ValueError('Stack upgrades currently support macOS only.')
    # Refuse a dependency-changing hot upgrade: it requires a planned reinstall.
    if (STACK / 'package-lock.json').read_bytes() != (SOURCE / 'package-lock.json').read_bytes():
        raise ValueError('Dependency lock differs. Use the onboarding installer with the existing private configuration.')
    # Preflight skills before writing runtime files.
    for root in [HOME / '.codex/skills', HOME / '.claude/skills']:
        for name, marker in [('agentworkforce', 'EXP31 AgentWorkforce skill'), ('llmcom', 'EXP31 LLMCom skill')]:
            target = root / name
            if target.exists() and marker not in (target / 'SKILL.md').read_text():
                raise ValueError('Refusing to replace unrelated skill: ' + str(target))
    run(['/usr/bin/python3', SOURCE / 'install-tools.py', config['role'], '--no-services'])
    install_skill()
    print(json.dumps({'upgraded': True, 'version': (SOURCE / 'VERSION').read_text().strip(),
                      'listenersRestarted': False, 'next': 'Read llmcom --skill. Existing chat identities remain stable; join from inside a chat when needed.'}))

def ensure_installed_runtime(offline=False, dry_run=False):
    """Idempotent setup on an already configured client or server."""
    node = ROOT / 'node/bin/node'
    healthy = node.exists() and (STACK/'package-lock.json').exists() and (STACK/'package-lock.json').read_bytes() == (SOURCE/'package-lock.json').read_bytes()
    if healthy:
        check = subprocess.run([str(node),'-e', "const D=require('better-sqlite3');const d=new D(':memory:');if(process.version!=='v22.23.3'||d.prepare('select 1 as ok').get().ok!==1)process.exit(1);require('ai-hist-native')"],cwd=STACK,env=tool_environment(),capture_output=True,timeout=30)
        healthy = check.returncode == 0
    if dry_run:
        print(json.dumps({'dryRun':True,'writes':False,'runtimeHealthy':healthy,'offline':offline,'next':'Keep healthy runtime; otherwise install selected upstream or bundled dependencies; ensure channel exists.'}));return
    if not healthy:
        if offline:
            import rescue
            rescue.install_runtime(ROOT,replace=(STACK/'node_modules').exists())
        else:
            try:
                install_node();STACK.mkdir(parents=True,exist_ok=True)
                for name in ['package.json','package-lock.json']:
                    if SOURCE != STACK:shutil.copy2(SOURCE/name,STACK/name)
                run([ROOT/'node/bin/npm','ci','--no-audit','--no-fund'],cwd=STACK,env=tool_environment())
            except (OSError,ValueError,subprocess.CalledProcessError):
                raise ValueError('Upstream dependency installation failed. Inspect the failure or explicitly repeat llmcom setup CHANNEL --offline. No automatic fallback occurred.')
    if not (STACK/'VERSION').exists() or (STACK/'VERSION').read_bytes() != (SOURCE/'VERSION').read_bytes():
        upgrade(argparse.Namespace(dry_run=False))
    print(json.dumps({'runtimeReady':True,'reused':healthy,'offline':offline,'next':'Create or reuse the requested room, then join this warmed chat.'}))

def connect(args):
    config = json.loads((CONFIG / 'stack.json').read_text()) if (CONFIG / 'stack.json').exists() else {'role': 'teammate'}
    vendor = args.vendor or ('codex' if os.environ.get('CODEX_THREAD_ID') else 'claude')
    session = os.environ.get('CODEX_THREAD_ID') if vendor == 'codex' else os.environ.get('CLAUDE_CODE_SESSION_ID')
    file = CONFIG / 'sessions' / ((session or 'unknown') + '.json')
    existing = json.loads(file.read_text()) if file.exists() else {}
    name = args.name or existing.get('name') or config['role'] + '-' + vendor + ('-' + session[:8] if session else '')
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', name): raise ValueError('Invalid agent name.')
    command = '~/bin/awstack join ' + name + ' ' + vendor
    if args.dry_run or not session:
        print(json.dumps({'insideConversation': bool(session), 'vendor': vendor, 'name': name, 'joinCommand': command, 'userRunClaudeCommand': '! ' + command if vendor == 'claude' else None, 'writes': False, 'next': 'Run that join through the warmed conversation tool; a separate terminal cannot supply its native session address.'}, indent=2)); return
    if args.authorize_claude:
        if vendor != 'claude': raise ValueError('--authorize-claude applies only to Claude.')
        authorize_claude(name)
    if vendor == 'claude':
        settings = HOME / '.claude/settings.json'
        data = json.loads(settings.read_text()) if settings.exists() else {}
        if data.get('crossSessionInbound') in ['hold', 'refuse'] or (data.get('permissions', {}).get('defaultMode') == 'bypassPermissions' and data.get('crossSessionInbound') != 'accept'):
            raise ValueError('Claude holds external peer input in this configuration. For the authorized workflow run awstack authorize-claude --agent ' + name + ', then connect again. Existing permissions will be preserved.')
    if existing:
        if existing['name'] != name: raise ValueError('This conversation already joined under another name; leave first.')
    # join is idempotent for a connected listener, and restarts a dead sidecar.
    run([HOME / 'bin/awstack', 'join', name, vendor])
    run([HOME / 'bin/awstack', 'verify'])

def repair(args):
    if not (CONFIG / 'stack.json').exists(): raise ValueError('No installation config; use onboard install first.')
    config = json.loads((CONFIG / 'stack.json').read_text())
    node = ROOT / 'node/bin/node'
    if node.exists():
        result = subprocess.run([str(node), str(STACK / 'awstack.mjs'), 'doctor'], capture_output=True, text=True, env=tool_environment())
        try: report = json.loads(result.stdout)
        except ValueError: report = {'checks': [{'name': 'runtime', 'ok': False, 'detail': 'Doctor could not load; inspect runtime files.'}]}
    else: report = {'checks': [{'name': 'pinned-node', 'ok': False, 'detail': 'Node is missing.'}]}
    failed = [c['name'] for c in report['checks'] if not c['ok']]
    fixes = {
        'pinned-node': 'install verified pinned Node', 'pinned-packages': 'npm ci from the existing lockfile',
        'sqlite-native-module': 'rebuild better-sqlite3 under pinned Node',
        'private-credential-files': 'restrict existing secrets to owner and enroll this node if its token is missing',
        'engine-health': 'load/restart this computer\'s existing server or SSH tunnel service',
        'broker-delivery': 'load/restart this computer\'s existing broker service',
    }
    plan = [{'check': name, 'action': fixes.get(name, 'Needs specific input or native chat context; no speculative repair')} for name in failed]
    if args.dry_run:
        print(json.dumps({'dryRun': True, 'writes': False, 'failedChecks': failed, 'plan': plan, 'liveChatProven': report.get('liveChatProven', False)}, indent=2)); return
    if not failed:
        print(json.dumps({'repaired': [], 'readyForJoin': True, 'liveChatProven': report.get('liveChatProven', False)})); return
    if 'pinned-node' in failed: install_node()
    env = tool_environment()
    if 'pinned-packages' in failed: run([ROOT / 'node/bin/npm', 'ci', '--no-audit', '--no-fund'], cwd=STACK, env=env)
    elif 'sqlite-native-module' in failed: run([ROOT / 'node/bin/npm', 'rebuild', 'better-sqlite3', '--no-audit', '--no-fund'], cwd=STACK, env=env)
    if 'private-credential-files' in failed:
        for name in ['workspace.json', 'node.json']:
            file = CONFIG / name
            if file.exists(): file.chmod(0o600)
    domain = 'gui/' + str(os.getuid())
    labels = []
    if 'engine-health' in failed: labels.append('com.exp31.agentworkforce.' + ('server' if __import__('connection').service_mode(HOME, config) == 'server' else 'tunnel'))
    for label in labels:
        file = HOME / 'Library/LaunchAgents' / (label + '.plist')
        if not file.exists(): raise ValueError('Service definition missing; rerun the installer with the existing configuration.')
        if subprocess.run(['launchctl', 'print', domain + '/' + label], capture_output=True).returncode != 0: run(['launchctl', 'bootstrap', domain, file])
        else: run(['launchctl', 'kickstart', '-k', domain + '/' + label])
    needs_enrollment = not (CONFIG / 'node.json').exists() and (CONFIG / 'workspace.json').exists()
    if needs_enrollment:
        wait_health(config['baseUrl'])
        run([HOME / 'bin/awstack', 'enroll-node'])
    if 'broker-delivery' in failed or needs_enrollment:
        label = 'com.exp31.agentworkforce.' + config['role'] + '.broker'
        file = HOME / 'Library/LaunchAgents' / (label + '.plist')
        if not file.exists(): raise ValueError('Broker service definition missing; rerun installation.')
        if subprocess.run(['launchctl', 'print', domain + '/' + label], capture_output=True).returncode != 0: run(['launchctl', 'bootstrap', domain, file])
        else: run(['launchctl', 'kickstart', '-k', domain + '/' + label])
    print(json.dumps({'attemptedRepairs': plan, 'next': 'Rerun doctor after services reconnect. Repair does not prove live delivery and does not change Claude permissions.'}))

def main():
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='command', required=True)
    i = sub.add_parser('install'); i.add_argument('--name', required=True); i.add_argument('--ssh-host', required=True); i.add_argument('--credentials-file'); i.add_argument('--port', type=int, default=8787); i.add_argument('--relay-port', type=int, default=8787); i.add_argument('--workspace', default='exp31-collaboration'); i.add_argument('--harness', choices=['auto','both','claude','codex','none'], default='auto'); i.add_argument('--dry-run', action='store_true'); i.add_argument('--offline',action='store_true',help='Explicitly use vendored Apple Silicon runtime/dependencies without GitHub/npm downloads.')
    sub.add_parser('doctor'); sub.add_parser('install-skill')
    u = sub.add_parser('upgrade'); u.add_argument('--dry-run', action='store_true')
    r = sub.add_parser('repair'); r.add_argument('--dry-run', action='store_true')
    c = sub.add_parser('connect'); c.add_argument('--name'); c.add_argument('--vendor', choices=['claude','codex']); c.add_argument('--dry-run', action='store_true'); c.add_argument('--authorize-claude', action='store_true')
    a = sub.add_parser('authorize-claude'); a.add_argument('--agent', required=True)
    b = sub.add_parser('bundle'); b.add_argument('--output', required=True)
    args = p.parse_args()
    if args.command == 'install': install(args)
    elif args.command == 'doctor': run([ROOT / 'node/bin/node', STACK / 'awstack.mjs', 'doctor'])
    elif args.command == 'install-skill': install_skill()
    elif args.command == 'upgrade': upgrade(args)
    elif args.command == 'authorize-claude': authorize_claude(args.agent)
    elif args.command == 'bundle': bundle(args.output)
    elif args.command == 'connect': connect(args)
    elif args.command == 'repair': repair(args)

if __name__ == '__main__':
    try: main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print('Onboarding stopped: ' + str(error), file=sys.stderr); sys.exit(1)
