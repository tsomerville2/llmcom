#!/usr/bin/env python3
"""Release maintainer: build a public, self-contained Apple Silicon rescue snapshot."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor

SOURCE = Path(__file__).resolve().parent
UPSTREAM = [('relaycast', '@relaycast/engine', '8.16.0'), ('relay', 'agent-relay', '13.0.1'),
            ('trajectories', 'agent-trajectories', '0.7.0'), ('relayhistory', 'ai-hist', '0.33.0'),
            ('flows', 'relayflows', '2.0.38')]

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()

def upstream_snapshot(item, output):
    repo, package, version = item
    data = json.load(urllib.request.urlopen('https://registry.npmjs.org/' + package + '/' + version, timeout=30))
    commit = data.get('gitHead')
    exact = bool(commit)
    url = 'https://github.com/AgentWorkforce/' + repo + '.git'
    if not commit:
        refs = subprocess.check_output(['git', 'ls-remote', '--tags', url, '*'+version+'*'], text=True).splitlines()
        refs = [r for r in refs if r.split()[1].removesuffix('^{}').split('/')[-1] in [version, 'v'+version]]
        if refs:
            commit = next((r.split()[0] for r in refs if r.endswith('^{}')), refs[0].split()[0]); exact = True
        else:
            commit = subprocess.check_output(['git', 'ls-remote', url, 'HEAD'], text=True).split()[0]
    name = repo + '-' + commit + '.tar.gz'
    archive = output / name
    urllib.request.urlretrieve('https://codeload.github.com/AgentWorkforce/' + repo + '/tar.gz/' + commit, archive)
    notices = []
    with tarfile.open(archive) as t:
        for m in t.getmembers():
            if m.isfile() and len(Path(m.name).parts) == 2 and Path(m.name).name.upper().startswith(('LICENSE', 'NOTICE', 'COPYING')):
                target = output / (repo + '-' + Path(m.name).name)
                target.write_bytes(t.extractfile(m).read()); notices.append(target.name)
    if not notices:
        if data.get('license') != 'MIT': raise ValueError('No upstream license/notice found for ' + repo)
        target = output / (repo + '-LICENSE-DECLARATION.json')
        target.write_text(json.dumps({'package':package,'version':version,'license':data['license'],
                                     'note':'Upstream declares MIT in package metadata; no root license file was provided. Original metadata is retained in the source archive.'},indent=2)+'\n')
        notices.append(target.name)
    with tarfile.open(archive) as t:
        directory = data.get('repository', {}).get('directory', '') if isinstance(data.get('repository'),dict) else ''
        matches = [m for m in t.getmembers() if m.isfile() and '/'.join(Path(m.name).parts[1:]) == (directory+'/' if directory else '')+'package.json']
        if matches and json.load(t.extractfile(matches[0])).get('version') != version: exact=False
    return {'repository': url, 'package': package, 'version': version, 'commit': commit,
            'exactReleaseSource': exact, 'archive': name, 'sha256': sha(archive), 'notices': notices}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepared-stack', help='An isolated fresh npm-ci stack; never pass a personal runtime directory.')
    p.add_argument('--node-archive', required=True)
    args = p.parse_args()
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise ValueError('Build this native rescue snapshot on an Apple Silicon Mac.')
    import onboard
    archive = Path(args.node_archive).resolve()
    if sha(archive) != onboard.NODE_HASHES['arm64']: raise ValueError('Official Node archive checksum mismatch.')
    output = SOURCE / 'rescue'
    if output.exists(): raise ValueError('Rescue snapshot already exists; move it aside before explicitly rebuilding.')
    output.mkdir()
    try:
        with tempfile.TemporaryDirectory(prefix='llmcom-vendor-build-') as d:
            tmp = Path(d)
            subprocess.run(['/usr/bin/tar', '-xzf', str(archive), '-C', d], check=True)
            node = tmp / ('node-v' + onboard.NODE_VERSION + '-darwin-arm64')
            stack = tmp / 'stack'; stack.mkdir()
            for name in ['package.json','package-lock.json']: shutil.copy2(SOURCE / name, stack / name)
            env = {k:v for k,v in os.environ.items() if not k.startswith(('CODEX_','CLAUDE_','RELAY_','AWSTACK_'))}
            env.update({'HOME':str(tmp / 'home'), 'PATH':str(node/'bin')+':/usr/bin:/bin:/usr/sbin:/sbin', 'DO_NOT_TRACK':'1'})
            (tmp/'home').mkdir()
            if args.prepared_stack:
                prepared = Path(args.prepared_stack).resolve()
                if 'llmcom-vendor-' not in str(prepared) or (prepared/'package-lock.json').read_bytes() != (SOURCE/'package-lock.json').read_bytes():
                    raise ValueError('Prepared input must be the isolated matching vendor build.')
                shutil.copytree(prepared/'node_modules', stack/'node_modules', symlinks=True)
            else:
                subprocess.run([str(node/'bin/npm'),'ci','--no-audit','--no-fund','--cache',str(tmp/'cache')], cwd=stack, env=env, check=True)
            # Keep same-architecture executables; record removed foreign broker binaries.
            excluded = []
            for path in (stack/'node_modules').rglob('agent-relay-broker-*'):
                if path.is_file() and path.parent.name == 'bin' and 'darwin-arm64' not in path.name:
                    excluded.append(str(path.relative_to(stack))); path.unlink()
            subprocess.run([str(node/'bin/node'),'-e', "const D=require('better-sqlite3'); const d=new D(':memory:'); if(d.prepare('select 1 as ok').get().ok!==1)process.exit(1)"],cwd=stack,env=env,check=True)
            lock = json.loads((SOURCE/'package-lock.json').read_text())
            packages = []
            for path, record in lock['packages'].items():
                descriptor = stack/path/'package.json'
                if path and descriptor.exists():
                    info=json.loads(descriptor.read_text())
                    packages.append({'path':path,'name':info.get('name'),'version':info.get('version'),
                                     'license':info.get('license',record.get('license')),'resolved':record.get('resolved'),
                                     'integrity':record.get('integrity')})
            (output/'packages.json').write_text(json.dumps(packages,indent=2)+'\n')
            sources_dir=output/'sources';sources_dir.mkdir()
            with ThreadPoolExecutor(max_workers=5) as pool: sources=list(pool.map(lambda item: upstream_snapshot(item,sources_dir),UPSTREAM))
            (output/'NOTICE.md').write_text('''# Vendored rescue attribution

This directory contains a separate emergency snapshot of Node.js and the npm packages listed in packages.json. The normal installer continues using upstream. Third-party code retains its original licenses and notices in the snapshot; source archives and root licenses are retained under sources/.

AgentWorkforce Relaycast, Agent Relay and Flows are Apache-2.0. Trajectories and RelayHistory are MIT. Node.js includes its own LICENSE covering Node and bundled third-party components. Transitive packages retain their license/notice files. Foreign-platform broker binaries were omitted; original files were otherwise retained. Exact package versions and provenance are recorded in the manifest and package list.

Source snapshots with exactReleaseSource=false are reference source from the recorded commit, not claimed to match the npm release. The installed npm artifacts are the exact pinned release tree. No private chat state, credentials, diaries or model files are included.
''')
            payload = tmp/'payload.tar.xz'
            print('Compressing the clean runtime and dependency tree...',flush=True)
            with payload.open('wb') as out:
                compressor=subprocess.Popen(['xz','-T2','-9','-c'],stdin=subprocess.PIPE,stdout=out)
                def clean(member):
                    member.uid=member.gid=0;member.uname=member.gname='';member.mtime=0
                    return member
                with tarfile.open(fileobj=compressor.stdin,mode='w|',format=tarfile.PAX_FORMAT) as t:
                    t.add(node,arcname='node',filter=clean)
                    t.add(stack/'node_modules',arcname='node_modules',filter=clean)
                compressor.stdin.close()
                if compressor.wait()!=0: raise ValueError('Compression failed.')
            parts=[]
            with payload.open('rb') as f:
                index=0
                while True:
                    data=f.read(20*1024*1024)
                    if not data:break
                    name='darwin-arm64.part'+str(index).zfill(3)
                    path=output/name;path.write_bytes(data)
                    parts.append({'file':name,'size':len(data),'sha256':sha(path)});index+=1
            manifest={'format':1,'nodeVersion':onboard.NODE_VERSION,'nodeAbi':'127',
                      'lockSha256':sha(SOURCE/'package-lock.json'),'platforms':{'darwin-arm64':{'parts':parts,'sha256':sha(payload)}},
                      'sources':sources,'excludedForeignBinaries':excluded,'packages':len(packages),
                      'artifactFiles':{str(p.relative_to(output)):sha(p) for p in output.rglob('*') if p.is_file() and '.part' not in p.name}}
            (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
            total=sum(p.stat().st_size for p in output.rglob('*') if p.is_file())
            print(json.dumps({'vendored':True,'packages':len(packages),'payloadBytes':payload.stat().st_size,'totalBytes':total,'platform':'darwin-arm64'}),flush=True)
    except BaseException:
        shutil.rmtree(output);raise

if __name__=='__main__':main()
