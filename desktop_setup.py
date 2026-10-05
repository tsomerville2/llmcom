"""Idempotent Claude Desktop MCP registration, without changing permissions."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import time


def install_claude(home, script, dry_run=False):
    home, script = Path(home), Path(script).resolve()
    if not script.is_file():
        raise ValueError('Desktop adapter missing. Upgrade the LLMCom runtime first.')
    target = home/'Library/Application Support/Claude/claude_desktop_config.json'
    before = target.read_bytes() if target.exists() else None
    data = json.loads(before) if before else {}
    if not isinstance(data,dict) or not isinstance(data.get('mcpServers',{}),dict):
        raise ValueError('Claude Desktop configuration is not a valid MCP server mapping.')
    servers = data.setdefault('mcpServers',{})
    entry = {'command':'/usr/bin/python3','args':[str(script)]}
    if servers.get('llmcom') == entry:
        return {'changed':False,'configured':True,'delivery':'on-demand tools only; native wake not proven'}
    if 'llmcom' in servers:
        raise ValueError('An existing llmcom MCP entry differs. Refusing to replace it.')
    servers['llmcom'] = entry
    if dry_run:
        return {'changed':False,'dryRun':True,'config':str(target),'server':'llmcom','delivery':'on-demand tools only'}
    target.parent.mkdir(parents=True,exist_ok=True)
    backup = None
    if before is not None:
        backup = target.with_name(target.name+'.llmcom-backup-'+str(time.time_ns()))
        descriptor = os.open(backup,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(descriptor,'wb') as stream: stream.write(before)
    descriptor, temporary = tempfile.mkstemp(prefix='.llmcom-',dir=target.parent)
    try:
        with os.fdopen(descriptor,'w') as stream:
            json.dump(data,stream,indent=2);stream.write('\n')
        current = target.read_bytes() if target.exists() else None
        if current != before:
            raise ValueError('Claude configuration changed during setup. Retry after its edit completes.')
        os.replace(temporary,target)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)
    return {'changed':True,'configured':True,'backup':str(backup) if backup else None,
            'next':'Reload Claude Desktop MCP servers or restart the app when convenient. Test llmcom_channels. This registration does not prove live delivery.'}
