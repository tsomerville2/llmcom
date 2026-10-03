"""Offline regression checks for onboarding boundaries, using disposable homes."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parent

class OnboardingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        spec = importlib.util.spec_from_file_location('onboard_test', SOURCE / 'onboard.py')
        self.module = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.module)
        m = self.module
        m.HOME = self.home; m.ROOT = self.home / '.local/share/agentworkforce'
        m.STACK = m.ROOT / 'stack'; m.CONFIG = self.home / '.config/agentworkforce'
        m.STATE = self.home / '.local/state/agentworkforce'
        self.env = {k:v for k,v in os.environ.items() if not k.startswith(('CODEX_', 'CLAUDE_'))}
        self.env['HOME'] = str(self.home)
        self.env['PYTHONDONTWRITEBYTECODE'] = '1'

    def tearDown(self): self.tmp.cleanup()

    def cli(self, *args):
        return subprocess.run(['/usr/bin/python3', str(SOURCE / 'awstack'), *args], env=self.env, capture_output=True, text=True)

    def test_help_and_skill_need_no_runtime_or_writes(self):
        for flag in ['--help', '--skill']:
            result = self.cli(flag)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('awstack', result.stdout)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_friendly_help_preview_and_title_names(self):
        for flag in ['--help','--skill']:
            result = subprocess.run(['/usr/bin/python3', str(SOURCE/'llmcom'), flag], env=self.env, capture_output=True, text=True)
            self.assertEqual(result.returncode,0,result.stderr); self.assertIn('llmcom',result.stdout)
        spec = importlib.util.spec_from_file_location('friendly_test', SOURCE/'llmcom.py')
        friendly = importlib.util.module_from_spec(spec)
        import sys
        sys.path.insert(0,str(SOURCE))
        try: spec.loader.exec_module(friendly)
        finally: sys.path.pop(0)
        self.assertEqual(friendly.generated_name('Renamed Chat','travis','claude','2029c608-uuid'),'travis-claude-renamed-chat-2029c608')
        self.assertEqual(friendly.generated_name('Design a live cross-agent channel | EXP31-pi-dev-tools','t','codex','01a0ffc0-uuid'),'t-codex-design-a-live-cross-agent-channel-01a0ffc0')
        self.assertEqual(friendly.channel_name('#channel-A'),'channel-a')
        friendly.HOME = self.home
        registry = self.home / '.claude/sessions'; registry.mkdir(parents=True)
        (registry/'42.json').write_text(json.dumps({'sessionId':'native-id','name':'Renamed Claude Chat'}))
        self.assertEqual(friendly.chat_title('claude','native-id'),'Renamed Claude Chat')
        (registry/'42.json').unlink(); registry.rmdir(); registry.parent.rmdir()
        result = subprocess.run(['/usr/bin/python3', str(SOURCE/'llmcom'), 'join','channel-A','--dry-run','--title','My Renamed Chat'],env=self.env,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr); self.assertFalse(json.loads(result.stdout)['writes'])
        self.assertEqual(list(self.home.iterdir()), [])

    def test_preview_and_external_connect_do_not_write(self):
        result = self.cli('onboard', 'install', '--name', 'alice', '--ssh-host', 'bertha', '--credentials-file', 'not-read-in-preview', '--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)['writes'])
        result = self.cli('connect', '--name', 'alice-claude', '--vendor', 'claude')
        value = json.loads(result.stdout)
        self.assertFalse(value['insideConversation']); self.assertFalse(value['writes'])
        self.assertEqual(value['joinCommand'], '~/bin/awstack join alice-claude claude')
        self.assertEqual(list(self.home.iterdir()), [])

    def test_wrapper_collision_stops_before_config_write(self):
        (self.home / 'bin').mkdir(); target = self.home / 'bin/awstack'; target.write_text('unrelated')
        result = subprocess.run(['/usr/bin/python3', str(SOURCE / 'install-tools.py'), 'alice', '--no-services'], env=self.env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(target.read_text(), 'unrelated'); self.assertFalse(self.module.CONFIG.exists())

    def test_install_preserves_settings_and_rejects_role_switch(self):
        self.module.private_json(self.module.CONFIG / 'stack.json', {'role':'alice', 'workspace':'existing', 'custom':{'keep':True}})
        command = ['/usr/bin/python3', str(SOURCE / 'install-tools.py'), 'alice', '--no-services']
        subprocess.run(command, env=self.env, check=True, capture_output=True)
        data = json.loads((self.module.CONFIG / 'stack.json').read_text())
        self.assertEqual(data['workspace'], 'existing'); self.assertEqual(data['custom'], {'keep':True})
        result = subprocess.run(command[:-2] + ['bob', '--no-services'], env=self.env, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads((self.module.CONFIG / 'stack.json').read_text())['role'], 'alice')

    def test_credentials_strip_peer_tokens_and_refuse_workspace_switch(self):
        given = self.home / 'access.json'
        given.write_text(json.dumps({'apiKey':'a'*32, 'agents':{'peer':{'token':'never distribute'}}}))
        self.module.import_credentials(given)
        target = self.module.CONFIG / 'workspace.json'; data = json.loads(target.read_text())
        self.assertEqual(data['agents'], {}); self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        given.write_text(json.dumps({'apiKey':'b'*32}))
        with self.assertRaises(ValueError): self.module.import_credentials(given)
        self.assertEqual(json.loads(target.read_text())['apiKey'], 'a'*32)

    def test_claude_merge_is_exact_and_preserves_user_settings(self):
        m = self.module; m.private_json(m.CONFIG / 'stack.json', {'baseUrl':'http://127.0.0.1:8787', 'sshHost':'bertha'})
        p = self.home / '.claude/settings.json'
        m.private_json(p, {'cleanupPeriodDays':36500, 'permissions':{'defaultMode':'auto','allow':['Bash(git status)']}, 'autoMode':{'allow':['$defaults','existing rule']}})
        with contextlib.redirect_stdout(io.StringIO()): m.authorize_claude('alice-claude')
        data = json.loads(p.read_text())
        self.assertEqual(data['permissions']['defaultMode'], 'auto')
        self.assertIn('Bash(git status)', data['permissions']['allow'])
        self.assertIn('Bash(~/bin/awstack join alice-claude claude)', data['permissions']['allow'])
        self.assertNotIn('Bash(*)', data['permissions']['allow'])
        self.assertIn('$defaults', data['autoMode']['allow']); self.assertEqual(data['cleanupPeriodDays'], 36500)
        self.assertEqual(data['crossSessionInbound'], 'accept')
        self.assertTrue(list(p.parent.glob('*.bak')))
        backup_count=len(list(p.parent.glob('*.bak')))
        with contextlib.redirect_stdout(io.StringIO()):m.authorize_claude('alice-claude')
        self.assertEqual(len(list(p.parent.glob('*.bak'))),backup_count)
        self.assertEqual(json.loads(p.read_text()),data)

    def test_bundle_excludes_secrets_and_runtime(self):
        output = self.home / 'kit.zip'
        with contextlib.redirect_stdout(io.StringIO()): self.module.bundle(output)
        with zipfile.ZipFile(output) as archive:
            names = archive.namelist()
            self.assertIn('agentworkforce/awstack', names)
            self.assertIn('agentworkforce/references/runbook.md', names)
            self.assertFalse(any('workspace.json' in n or 'node_modules/' in n or 'evidence/' in n for n in names))

    def test_upgrade_is_read_only_in_preview_and_retains_sessions(self):
        m = self.module
        m.private_json(m.CONFIG / 'stack.json', {'role':'alice', 'workspace':'existing', 'custom':{'keep':True}})
        m.STACK.mkdir(parents=True)
        (m.STACK / 'package-lock.json').write_bytes((SOURCE / 'package-lock.json').read_bytes())
        record = m.CONFIG / 'sessions/native.json'
        m.private_json(record, {'name':'alice-chat', 'pid':12345, 'door':{'token':'fixture'}})
        settings = self.home / '.claude/settings.json'
        m.private_json(settings, {'permissions':{'defaultMode':'auto'}})
        before = {p: p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        import argparse
        with contextlib.redirect_stdout(io.StringIO()): m.upgrade(argparse.Namespace(dry_run=True))
        self.assertEqual(before, {p: p.read_bytes() for p in self.home.rglob('*') if p.is_file()})
        calls = []
        def run_isolated(argv, **kwargs):
            calls.append([str(x) for x in argv])
            return subprocess.run([str(x) for x in argv], env=self.env, check=True, capture_output=True)
        with patch.object(m, 'run', run_isolated), patch.object(m.platform, 'system', return_value='Darwin'), contextlib.redirect_stdout(io.StringIO()):
            m.upgrade(argparse.Namespace(dry_run=False))
        self.assertEqual(record.read_bytes(), before[record])
        self.assertEqual(settings.read_bytes(), before[settings])
        self.assertTrue((self.home / '.claude/skills/llmcom/SKILL.md').exists())
        self.assertTrue(all('--no-services' in c for c in calls))
        self.assertEqual(json.loads((m.CONFIG / 'stack.json').read_text())['custom'], {'keep':True})

if __name__ == '__main__': unittest.main()
