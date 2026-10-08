"""CLI setup orchestrates existing provisioning and preserves failure boundaries."""
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
    def invoke(self,environment,argv=None,failure=None):
        output=io.StringIO()
        with patch.dict(os.environ,environment,clear=True),patch.object(sys,'argv',['llmcom','--setup',*(argv or [])]),patch('connector.main') as provision,patch('onboard.install_skill') as skill,patch('subprocess.run',side_effect=failure) as run,contextlib.redirect_stdout(output):
            cli.main()
        return output.getvalue(),provision,skill,run
    def test_terminal_prepares_without_browser_or_fake_join(self):
        output,provision,skill,run=self.invoke({})
        provision.assert_called_once_with(['enable','--channel','myphone','--add-channels','--client','claude','--no-open'])
        skill.assert_called_once();run.assert_not_called()
        self.assertIn('Run llmcom join myphone',output)
        self.assertIn('Request headers is missing',output)
    def test_agent_joins_actual_context_and_selected_room(self):
        output,provision,skill,run=self.invoke({'CODEX_THREAD_ID':'existing-thread'},['#David'])
        self.assertEqual(run.call_args.args[0][-2:],['join','david'])
        self.assertTrue(run.call_args.kwargs['check'])
        self.assertIn('round trip still need verification',output)
    def test_join_failure_is_not_reported_as_success(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.invoke({'CLAUDE_CODE_SESSION_ID':'existing-thread'},failure=subprocess.CalledProcessError(1,['join']))
    def test_open_is_explicit(self):
        output,provision,skill,run=self.invoke({},['--open','--client','openai'])
        self.assertNotIn('--no-open',provision.call_args.args[0])
        self.assertIn('setup#openai',output)
    def test_invalid_room_never_provisions(self):
        with patch('connector.main') as provision:
            with self.assertRaises(ValueError):self.invoke({},['bad room'])
            provision.assert_not_called()
