"""Explicit offline dependency restore from release-vendored artifacts."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import posixpath
import shutil
import subprocess
import tarfile
import tempfile
import uuid

SOURCE = Path(__file__).resolve().parent

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()

def current_platform():
    return ('darwin' if platform.system() == 'Darwin' else platform.system().lower()) + '-' + {'x86_64':'x64'}.get(platform.machine(), platform.machine())

def manifest():
    path = SOURCE / 'rescue/manifest.json'
    if not path.exists(): raise ValueError('This distribution has no rescue data. Obtain the complete llmcom wheel or GitHub release while available.')
    data = json.loads(path.read_text())
    if data.get('format') != 1: raise ValueError('Unsupported rescue manifest format.')
    if sha(SOURCE / 'package-lock.json') != data.get('lockSha256'): raise ValueError('Rescue snapshot does not match this release lockfile.')
    if data.get('nodeVersion') != '22.23.3' or data.get('nodeAbi') != '127': raise ValueError('Unexpected rescue Node version/ABI.')
    return data

def artifact_path(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts: raise ValueError('Unsafe rescue artifact path.')
    result = SOURCE / 'rescue' / name
    if not result.exists():
        data_root = os.environ.get('LLMCOM_RESCUE_DATA_PATH')
        if not data_root:
            try:
                import llmcom_rescue_data
                data_root = str(Path(llmcom_rescue_data.__file__).parent / '_data')
            except ImportError: pass
        if data_root: result = Path(data_root) / name
    if result.is_symlink() or not result.is_file(): raise ValueError('Missing or unsafe rescue artifact: ' + name)
    return result

def copy_artifacts(destination):
    data = manifest()
    destination = Path(destination)
    shutil.copytree(SOURCE/'rescue',destination,dirs_exist_ok=True)
    for record in data['platforms'].values():
        for part in record['parts']:
            target=destination/part['file']
            if not target.exists():shutil.copy2(artifact_path(part['file']),target)

def verify(data, target=None):
    for name, digest in data['artifactFiles'].items():
        if sha(artifact_path(name)) != digest: raise ValueError('Rescue checksum mismatch: ' + name)
    platforms = [target] if target else list(data['platforms'])
    for name in platforms:
        if name not in data['platforms']:
            raise ValueError('Offline rescue supports ' + ', '.join(data['platforms']) + '; this computer is ' + name + '. Use normal upstream setup on this architecture.')
        h = hashlib.sha256()
        for part in data['platforms'][name]['parts']:
            path = artifact_path(part['file'])
            if path.stat().st_size != part['size'] or sha(path) != part['sha256']: raise ValueError('Rescue checksum mismatch: ' + part['file'])
            with path.open('rb') as f:
                for block in iter(lambda: f.read(1024*1024), b''): h.update(block)
        if h.hexdigest() != data['platforms'][name]['sha256']: raise ValueError('Combined rescue payload checksum mismatch.')

def safe_extract(archive, destination):
    """Validate the entire archive before extracting; retain safe npm .bin links."""
    with tarfile.open(archive, 'r:xz') as t:
        members = t.getmembers()
        names = set(); links = set()
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] not in ['node', 'node_modules']:
                raise ValueError('Unsafe path in rescue archive: ' + member.name)
            if member.name in names: raise ValueError('Duplicate rescue archive member: ' + member.name)
            names.add(member.name)
            if not (member.isfile() or member.isdir() or member.issym() or member.islnk()): raise ValueError('Unsupported rescue archive member.')
            if member.issym() or member.islnk():
                if member.linkname.startswith('/'): raise ValueError('Absolute rescue archive link.')
                target = posixpath.normpath(posixpath.join(posixpath.dirname(member.name), member.linkname) if member.issym() else member.linkname)
                if PurePosixPath(target).parts[0] not in ['node','node_modules'] or '..' in PurePosixPath(target).parts:
                    raise ValueError('Rescue archive link escapes its root.')
                links.add(member.name)
        for member in members:
            if any(str(parent) in links for parent in PurePosixPath(member.name).parents):
                raise ValueError('Rescue member descends through an archive link.')
        for member in members:
            if member.isdir():
                (destination / member.name).mkdir(parents=True, exist_ok=True)
        for member in members:
            path = destination / member.name
            path.parent.mkdir(parents=True, exist_ok=True)
            if member.isfile():
                with path.open('xb') as out: shutil.copyfileobj(t.extractfile(member), out)
                path.chmod(member.mode & 0o777)
        for member in members:
            path = destination / member.name
            if member.issym(): path.symlink_to(member.linkname)
            elif member.islnk(): os.link(destination / member.linkname, path)

def validate_runtime(stage, env):
    node = stage / 'node/bin/node'; modules = stage / 'node_modules'
    version = subprocess.check_output([str(node), '--version'], env=env, text=True).strip()
    if version != 'v22.23.3': raise ValueError('Restored Node version mismatch.')
    script = "const D=require('better-sqlite3');const d=new D(':memory:');if(process.versions.modules!=='127'||d.prepare('select 1 as ok').get().ok!==1)process.exit(1);require('ai-hist-native');console.log('rescue native modules OK')"
    subprocess.run([str(node), '-e', script], cwd=modules.parent, env=env, check=True, timeout=30)

def install_runtime(root, dry_run=False, replace=False):
    data = manifest(); target = current_platform()
    verify(data, target)
    root = Path(root)
    modules = root / 'stack/node_modules'
    lock = root / 'stack/package-lock.json'
    node_link = root / 'node'
    if node_link.exists() and not node_link.is_symlink(): raise ValueError('Refusing to replace an unrelated node directory.')
    if modules.exists() and not replace:
        if lock.exists() and sha(lock) == data['lockSha256'] and (node_link/'bin/node').exists():
            print(json.dumps({'reused':True,'offline':True,'platform':target,'next':'Continue through the idempotent setup command.'})); return
        raise ValueError('Existing dependencies require an explicit offline setup repair; the replacement will retain a backup.')
    if dry_run:
        print(json.dumps({'dryRun':True,'writes':False,'offline':True,'platform':target,'nodeVersion':data['nodeVersion'],'packages':data['packages'],'replace':replace})); return
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.rescue-stage-', dir=root) as d:
        stage = Path(d)
        archive = stage/'payload.tar.xz'
        with archive.open('wb') as out:
            for part in data['platforms'][target]['parts']:
                with artifact_path(part['file']).open('rb') as f: shutil.copyfileobj(f,out)
        safe_extract(archive, stage)
        env = {k:v for k,v in os.environ.items() if not k.startswith(('CODEX_','CLAUDE_','RELAY_','AWSTACK_'))}
        (stage/'home').mkdir()
        env.update({'HOME':str(stage/'home'),'PATH':str(stage/'node/bin')+':/usr/bin:/bin:/usr/sbin:/sbin','DO_NOT_TRACK':'1'})
        validate_runtime(stage,env)
        (root/'stack').mkdir(exist_ok=True)
        suffix = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]
        final_node = root / ('node-v'+data['nodeVersion']+'-rescue-'+suffix)
        backup = root / 'rescue-backups' / suffix
        previous_link = os.readlink(node_link) if node_link.is_symlink() else None
        old_moved = False; new_moved = False
        try:
            if modules.exists():
                backup.mkdir(parents=True); modules.rename(backup/'node_modules'); old_moved=True
                for name in ['package.json','package-lock.json']:
                    if (root/'stack'/name).exists(): shutil.copy2(root/'stack'/name,backup/name)
            (stage/'node').rename(final_node)
            (stage/'node_modules').rename(modules); new_moved=True
            temp_link = root / ('.node-'+suffix)
            temp_link.symlink_to(final_node); temp_link.replace(node_link)
            for name in ['package.json','package-lock.json']: shutil.copy2(SOURCE/name,root/'stack'/name)
            (root/'rescue-receipt.json').write_text(json.dumps({'offline':True,'platform':target,'nodeVersion':data['nodeVersion'],'payloadSha256':data['platforms'][target]['sha256'],'restoredAt':datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2)+'\n')
        except BaseException:
            if new_moved: shutil.rmtree(modules)
            if old_moved:
                (backup/'node_modules').rename(modules)
                for name in ['package.json','package-lock.json']:
                    if (backup/name).exists(): shutil.copy2(backup/name,root/'stack'/name)
            if node_link.is_symlink(): node_link.unlink()
            if previous_link: node_link.symlink_to(previous_link)
            if final_node.exists(): shutil.rmtree(final_node)
            raise
    print(json.dumps({'restored':True,'offline':True,'platform':target,'nodeVersion':data['nodeVersion'],'packages':data['packages'],'previousDependencies':str(backup) if old_moved else None,
                      'next':'Run llmcom setup CHANNEL --offline with private SSH/credential arguments, or upgrade an existing configured stack. No chat or service was restarted.'}))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('status');sub.add_parser('verify')
    args=p.parse_args()
    data=manifest()
    if args.command=='verify':verify(data)
    print(json.dumps({'vendored':True,'verified':args.command=='verify','platforms':list(data['platforms']),'currentPlatform':current_platform(),'nodeVersion':data['nodeVersion'],'packages':data['packages'],'sources':len(data['sources']),'normalInstall':'llmcom setup CHANNEL --computer NAME --ssh-host SERVER --credentials-file FILE','offlineInstall':'llmcom setup CHANNEL --offline --computer NAME --ssh-host SERVER --credentials-file FILE'}))

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,subprocess.SubprocessError) as error:
        print('llmcom rescue: '+str(error),file=__import__('sys').stderr);raise SystemExit(1)
