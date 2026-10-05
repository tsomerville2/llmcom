"""Read-only connection discovery. Output is an explicit non-secret allowlist."""
import json
import os
from pathlib import Path
import re
import socket
import subprocess
from urllib.parse import urlparse


def discover(config_dir, session=None, resolve=None, home=None):
    config_dir = Path(config_dir)
    file = config_dir / 'stack.json'
    if not file.exists():
        raise ValueError('No saved connection. Obtain an invitation from a joined teammate; then run llmcom setup --help.')
    config = json.loads(file.read_text())
    workspace_file = config_dir / 'workspace.json'
    workspace_id = None
    if workspace_file.exists():
        workspace_id = json.loads(workspace_file.read_text()).get('workspaceId')
    from connection import service_mode, tunnel_route
    home = Path(home) if home else (config_dir.parent.parent if config_dir.parent.name == '.config' else Path.home())
    mode = service_mode(home, config)
    route = tunnel_route(home, config) if mode == 'client' else None
    destination = config.get('sshHost')
    if not destination or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9@._:-]*', destination):
        raise ValueError('Saved SSH destination is missing or invalid.')
    if resolve is None:
        def resolve(host):
            result = subprocess.run(['/usr/bin/ssh', '-G', host], capture_output=True, text=True, timeout=10)
            if result.returncode:
                raise ValueError('Cannot resolve SSH configuration. Check the saved host with ssh -G locally.')
            return result.stdout
    ssh = dict(line.split(None, 1) for line in resolve(destination).splitlines() if ' ' in line)
    records = []
    skipped = 0
    for path in sorted((config_dir / 'sessions').glob('*.json')):
        if path.name.endswith('.probe.json') or (session and path.stem != session):
            continue
        try:
            record = json.loads(path.read_text())
            if not isinstance(record, dict): raise ValueError('Invalid record')
        except (ValueError, OSError):
            skipped += 1
            continue
        if record.get('name'):
            records.append({k: record.get(k) for k in ['name', 'vendor', 'channels']})
    if session and not records:
        raise ValueError('Selected conversation has no valid joined record. Run llmcom sessions or use llmcom tui to select a joined conversation.')
    host = ssh.get('hostname', destination)
    return {
        'writes': False,
        'skippedInvalidSessionRecords': skipped,
        'conversationComputer': socket.gethostname(),
        'configuredComputerName': config.get('role'),
        'workspace': config.get('workspace'),
        'workspaceId': workspace_id,
        'serviceMode': mode,
        'conversations': records,
        'relay': {'sshAlias': destination, 'hostname': host, 'user': ssh.get('user'),
                  'sshPort': int(ssh.get('port', '22')),
                  'localForwardPort': urlparse(config.get('baseUrl', '')).port,
                  'remoteBind': '127.0.0.1', 'remotePort': config.get('relayPort', 8787),
                  'requiresJumpHost': ssh.get('proxyjump', 'none') != 'none',
                  'requiresProxyCommand': ssh.get('proxycommand', 'none') != 'none',
                  'portSource': 'saved configuration (legacy default 8787 if absent)',
                  **(route or {})},
        'reachability': 'Not tested. SSH configuration identifies a destination; it does not prove remote access.',
        'networkRequirements': 'Recipient needs a route to the SSH host and access to its SSH port. Keep the relay port private; clients use an SSH tunnel. LAN-only addresses require the same LAN or a VPN route. VPN addresses require authorized VPN access.',
        'accessRequirements': 'Each teammate needs their own authorized SSH access and a workspace credential file transferred privately. Private keys and workspace credentials are not included here.'
    }


def invitation(info, channel):
    """Portable instructions, not a credential or grant of access."""
    import shlex
    channels = {c for r in info['conversations'] for c in (r.get('channels') or [])}
    if channel not in channels:
        raise ValueError('Channel is not recorded for the selected conversations. Run discover and select a joined channel.')
    relay = info['relay']
    host = relay['hostname']
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]*', host):
        raise ValueError('Resolved host cannot be represented safely in an invitation.')
    if relay['requiresJumpHost'] or relay['requiresProxyCommand']:
        raise ValueError('This SSH route uses a jump host or proxy. Obtain a portable recipient route from its administrator before inviting; local proxy configuration is not copied.')
    if relay['remoteBind'] not in ['127.0.0.1', 'localhost']:
        raise ValueError('Relay uses a non-loopback SSH target. Recipient setup needs the administrator-provided route; refusing to generate a different destination.')
    if host in ['localhost', '127.0.0.1', '::1']:
        raise ValueError('The saved SSH host is loopback, which a teammate cannot use. Configure a reachable SSH hostname for this relay before inviting.')
    workspace = info.get('workspace')
    if not workspace:
        raise ValueError('Workspace name is missing from the saved connection.')
    setup = shlex.join(['llmcom', 'setup', channel, '--computer', 'YOUR-COMPUTER-NAME',
                        '--ssh-host', 'llmcom-invited-relay', '--workspace', workspace,
                        '--relay-port', str(relay['remotePort']), '--credentials-file', 'PRIVATE-CREDENTIAL-FILE'])
    return f'''Join my LLMCom channel {channel} in workspace {workspace} from your existing warmed conversation.
Expected workspace ID: {info.get('workspaceId') or 'not recorded; confirm with the host administrator'}. Check the privately supplied credential file against this ID before setup.
Install the CLI with pipx install llmcom, then read llmcom --skill and llmcom setup --help.
The relay SSH host is {host}, TCP port {relay['sshPort']}. The sender's SSH account is {relay['user']}; ask the host administrator which account YOU are authorized to use. The conversation computer is not necessarily this relay host.
{info['networkRequirements']}
{info['accessRequirements']}
Have the administrator authorize YOUR public SSH key; never send your private key. Obtain the workspace JSON credential file through an authenticated private transfer and chmod 600 that file. This invitation itself grants no access.
Configure an alias in YOUR ~/.ssh/config (replace YOUR-AUTHORIZED-USER and use your own key):
Host llmcom-invited-relay
    HostName {host}
    Port {relay['sshPort']}
    User YOUR-AUTHORIZED-USER
    IdentitiesOnly yes
    IdentityFile ~/.ssh/YOUR-OWN-KEY
Check ssh -o BatchMode=yes -o ConnectTimeout=5 llmcom-invited-relay true. Verify the server host-key fingerprint with its administrator; do not disable host-key checking.
If access fails, diagnose routing/VPN, SSH port reachability, and key authorization in that order. Do not open the relay port to the Internet.
After replacing the two uppercase placeholders, run:
{setup}
Then through this same warmed Claude Code or Codex chat run: llmcom join {shlex.quote(channel)}
Require an automatically delivered receipt probe and a two-way idle message before claiming live delivery. Keep existing identities and permissions. If another workspace is already configured, stop and report the conflict instead of overwriting it.
'''


def check_connection(info, run=subprocess.run):
    """Read-only checks using the owner's existing SSH trust and local tunnel."""
    import urllib.request
    relay=info['relay']
    try:
        result=run(['/usr/bin/ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=5',relay['sshAlias'],'true'],capture_output=True,text=True,timeout=8)
        if result.returncode==0:
            ssh={'ok':True,'detail':'Authenticated SSH command succeeded using existing host trust.'}
        else:
            error=result.stderr.lower()
            if 'host key verification failed' in error or 'remote host identification has changed' in error:
                reason='host-key';next_step='Verify the host fingerprint with its administrator, then establish trust interactively. Do not disable host-key checking.'
            elif 'permission denied' in error:
                reason='authorization';next_step='Have the host administrator authorize your public key and confirm your SSH username.'
            elif 'could not resolve' in error:
                reason='dns';next_step='Check the host name and VPN DNS. A sender-local SSH alias is not portable.'
            else:
                reason='reachability';next_step='Check VPN/LAN routing and the SSH port firewall; confirm the host is awake.'
            ssh={'ok':False,'reason':reason,'next':next_step}
    except (OSError,subprocess.TimeoutExpired):
        ssh={'ok':False,'reason':'timeout-or-unavailable','next':'Check SSH installation, routing, VPN access and whether the relay host is awake.'}
    port=relay.get('localForwardPort')
    health={'ok':False,'next':'Start or repair the configured SSH tunnel and relay, then rerun the check.'}
    if isinstance(port,int) and 1<=port<=65535:
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=3) as response:
                health={'ok':response.status==200,'detail':'Local relay health endpoint responded. This is not proof of live chat delivery.'}
        except (OSError,ValueError):pass
    return {'ssh':ssh,'relayHealth':health,'nativeChatDelivery':'Not tested by this command.'}
