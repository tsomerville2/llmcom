"""Determine infrastructure role from configuration, never a person's machine name."""
import plistlib
from pathlib import Path


def service_mode(home, config):
    explicit = config.get('serviceMode')
    if explicit is not None:
        if explicit not in ['server','client']:
            raise ValueError('Unknown serviceMode; expected server or client.')
        return explicit
    agents = Path(home)/'Library/LaunchAgents'
    file = agents/'com.exp31.agentworkforce.server.plist'
    if file.exists():
        with file.open('rb') as stream: service = plistlib.load(stream)
        if any(str(arg).endswith('/server.mjs') for arg in service.get('ProgramArguments', [])):
            return 'server'
    return 'client'


def tunnel_route(home, config):
    """Read this stack's saved launchd route, without exposing other SSH arguments."""
    file=Path(home)/'Library/LaunchAgents/com.exp31.agentworkforce.tunnel.plist'
    if not file.exists():return None
    with file.open('rb') as stream:service=plistlib.load(stream)
    args=service.get('ProgramArguments',[])
    if not args or Path(args[0]).name!='ssh':return None
    if args[-1]!=config.get('sshHost'):return None
    for i,arg in enumerate(args[:-1]):
        if arg!='-L':continue
        pieces=args[i+1].split(':')
        if len(pieces)==4 and pieces[0] in ['127.0.0.1','localhost'] and pieces[1].isdigit() and pieces[3].isdigit():
            local,remote=int(pieces[1]),int(pieces[3])
            if 1<=local<=65535 and 1<=remote<=65535:
                return {'localForwardPort':local,'remoteBind':pieces[2],'remotePort':remote,'source':'saved SSH tunnel service'}
    return None
