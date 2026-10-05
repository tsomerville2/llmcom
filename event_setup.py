"""Explicit private provisioning for one MCP event account; never print tokens."""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import tempfile


def provision(accounts_file, token_file, account, channels, dry_run=False):
    accounts_file,token_file=Path(accounts_file).expanduser(),Path(token_file).expanduser()
    if accounts_file.resolve()==token_file.resolve():raise ValueError('Use separate account and token files.')
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',account or ''):raise ValueError('Choose a short account name.')
    if not channels or any(not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}',c) for c in channels):raise ValueError('Specify at least one valid channel.')
    channels=sorted(set(channels))
    for private_file in [accounts_file, token_file]:
        if private_file.exists() and private_file.stat().st_mode & 0o077:
            raise ValueError('Existing credential files must be private (chmod 600).')
    before=accounts_file.read_bytes() if accounts_file.exists() else None
    accounts=json.loads(before) if before else {}
    if not isinstance(accounts,dict):raise ValueError('Invalid account file.')
    if account in accounts:
        if not token_file.exists():raise ValueError('Existing account has no supplied token file. Refusing silent credential rotation.')
        digest=hashlib.sha256(token_file.read_text().strip().encode()).hexdigest()
        if accounts[account]!={'tokenSha256':digest,'channels':channels}:raise ValueError('Existing account access or token differs; refusing replacement.')
        return {'created':False,'account':account,'channels':channels,'tokenFile':str(token_file),'secretsPrinted':False}
    if token_file.exists():raise ValueError('Token file already exists; choose an unused private path.')
    if dry_run:return {'writes':False,'account':account,'channels':channels,'accountsFile':str(accounts_file),'tokenFile':str(token_file)}
    for parent in [accounts_file.parent,token_file.parent]:parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    token=secrets.token_urlsafe(48)
    accounts[account]={'tokenSha256':hashlib.sha256(token.encode()).hexdigest(),'channels':channels}
    descriptor=os.open(token_file,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(descriptor,'w') as stream:stream.write(token+'\n')
    descriptor,temporary=tempfile.mkstemp(prefix='.llmcom-accounts-',dir=accounts_file.parent)
    try:
        with os.fdopen(descriptor,'w') as stream:json.dump(accounts,stream,indent=2);stream.write('\n')
        current=accounts_file.read_bytes() if accounts_file.exists() else None
        if current!=before:raise ValueError('Account configuration changed; retry with the saved token or reconcile manually.')
        if before is not None:
            backup=accounts_file.with_name(accounts_file.name+'.backup-'+secrets.token_hex(6))
            descriptor=os.open(backup,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(descriptor,'wb') as stream:stream.write(before)
        os.replace(temporary,accounts_file)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)
    return {'created':True,'account':account,'channels':channels,'accountsFile':str(accounts_file),'tokenFile':str(token_file),'secretsPrinted':False,
            'next':'Use this private bearer token only in the intended ChatGPT connector authentication. Start serve-events; configure HTTPS ingress separately. Do not paste tokens into channel invitations.'}
