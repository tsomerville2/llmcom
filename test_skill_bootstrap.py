import os
from pathlib import Path
import subprocess
import tempfile
import unittest
SOURCE=Path(__file__).parent.resolve()
class SkillBootstrapTests(unittest.TestCase):
    def test_cold_help_installs_refreshes_and_preserves_skills(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d);env=dict(os.environ,HOME=d)
            def run(*args):
                r=subprocess.run(['/usr/bin/python3',str(SOURCE/'llmcom'),*args],env=env,capture_output=True,text=True)
                self.assertEqual(r.returncode,0,r.stderr);return r
            r=run('--help');self.assertIn('https://llmcom-connector.fly.dev/setup',r.stdout)
            paths=[home/'.claude/skills/llmcom/SKILL.md',home/'.codex/skills/llmcom/SKILL.md']
            for p in paths:self.assertEqual(p.read_bytes(),(SOURCE/'LLMCOM-SKILL.md').read_bytes())
            stamp=paths[0].stat().st_mtime_ns;run('--help');self.assertEqual(stamp,paths[0].stat().st_mtime_ns)
            paths[0].write_text('<!-- EXP31 LLMCom skill -->\nstale')
            paths[1].write_text('Unrelated user skill')
            r=run('setup','--help');self.assertIn('llmcom --setup',r.stdout)
            self.assertEqual(paths[0].read_bytes(),(SOURCE/'LLMCOM-SKILL.md').read_bytes())
            self.assertEqual(paths[1].read_text(),'Unrelated user skill')
            self.assertIn('preserving unrelated',r.stderr)
            paths[0].unlink();run('--skill');self.assertTrue(paths[0].exists())
            self.assertFalse((home/'.config/agentworkforce').exists())
    def test_older_cli_does_not_downgrade_newer_skill(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'.codex/skills/llmcom';root.mkdir(parents=True)
            (root/'SKILL.md').write_text('<!-- EXP31 LLMCom skill -->\nfuture')
            (root/'.llmcom-version').write_text('999.0.0')
            r=subprocess.run(['/usr/bin/python3',str(SOURCE/'llmcom'),'--help'],env=dict(os.environ,HOME=d),capture_output=True,text=True)
            self.assertEqual(r.returncode,0);self.assertIn('future',(root/'SKILL.md').read_text())
