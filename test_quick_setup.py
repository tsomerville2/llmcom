"""Progressive setup keeps local work independent of optional phone failures."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('friendly_setup',Path(__file__).with_name('llmcom.py'))
cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
class QuickSetupTests(unittest.TestCase):
    def invoke(self,environment=None,argv=None,fail_stage=None,timeout=False):
        output=io.StringIO();errors=io.StringIO();calls=[]
        def run(command,**kw):
            stage=command[2];calls.append((command,kw))
            if stage==fail_stage:
                if timeout:raise subprocess.TimeoutExpired(command,60)
                raise subprocess.CalledProcessError(1,command)
        code=0
        with patch.dict(os.environ,environment or {},clear=True),patch.object(sys,'argv',['llmcom','--setup',*(argv or [])]),patch('onboard.ensure_skills') as skill,patch('subprocess.run',side_effect=run),contextlib.redirect_stdout(output),contextlib.redirect_stderr(errors):
            try:cli.main()
            except SystemExit as e:code=e.code
        return output.getvalue()+errors.getvalue(),calls,code,skill
    def test_terminal_local_first_without_fake_join(self):
        out,calls,code,skill=self.invoke()
        self.assertEqual([c[0][2] for c in calls],['setup','connector'])
        self.assertEqual(calls[0][0][-2:],['setup','myphone'])
        self.assertNotIn('--local',calls[0][0]) # reuse existing workspace, including remote
        self.assertIn('--no-open',calls[1][0]);self.assertEqual(calls[1][1]['timeout'],60)
        self.assertEqual(code,0);skill.assert_called_once()
        self.assertIn('run-inside-coding-chat',out)
    def test_agent_joins_before_phone(self):
        out,calls,code,_=self.invoke({'CODEX_THREAD_ID':'thread'},['#David'])
        self.assertEqual([c[0][2] for c in calls],['setup','join','connector'])
        self.assertEqual(calls[1][0][-2:],['join','david'])
        self.assertIn('"localJoin": "joined"',out);self.assertEqual(code,0)
    def test_gateway_failure_is_nonfatal_after_local_join(self):
        out,calls,code,_=self.invoke({'CODEX_THREAD_ID':'thread'},fail_stage='connector')
        self.assertEqual(code,0);self.assertIn('"localJoin": "joined"',out)
        self.assertIn('"phoneSetup": "deferred"',out)
        self.assertIn('llmcom phone myphone',out);self.assertNotIn('PHONE: Enable',out)
    def test_gateway_timeout_retains_local_progress(self):
        out,calls,code,_=self.invoke(fail_stage='connector',timeout=True)
        self.assertEqual(code,0);self.assertIn('"workspaceReady": true',out)
        self.assertIn('"phoneSetup": "deferred"',out)
    def test_local_failure_is_fatal_and_phone_not_attempted(self):
        with self.assertRaises(subprocess.CalledProcessError):self.invoke(fail_stage='setup')
    def test_join_failure_remains_visible_while_phone_can_progress(self):
        out,calls,code,_=self.invoke({'CLAUDE_CODE_SESSION_ID':'thread'},fail_stage='join')
        self.assertEqual(code,2);self.assertIn('"localJoin": "failed"',out)
        self.assertEqual(calls[-1][0][2],'connector')
    def test_local_only_never_calls_gateway(self):
        out,calls,code,_=self.invoke({'CODEX_THREAD_ID':'thread'},['--local-only'])
        self.assertEqual([c[0][2] for c in calls],['setup','join'])
        self.assertIn('"phoneSetup": "skipped"',out);self.assertEqual(code,0)
    def test_open_is_explicit(self):
        out,calls,code,_=self.invoke(argv=['--open','--client','openai'])
        self.assertNotIn('--no-open',calls[-1][0]);self.assertIn('setup#openai',out)
    def test_invalid_room_never_provisions(self):
        with self.assertRaises(ValueError):self.invoke(argv=['bad room'])
