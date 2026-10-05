import json
from pathlib import Path
import tempfile
import unittest
from desktop_setup import install_claude

class SetupTests(unittest.TestCase):
    def test_merge_backup_idempotent_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            home=Path(directory); script=home/'desktop.py';script.write_text('')
            target=home/'Library/Application Support/Claude/claude_desktop_config.json'
            target.parent.mkdir(parents=True)
            original={'mcpServers':{'existing':{'command':'keep'}},'preferences':{'keep':True}}
            target.write_text(json.dumps(original));before=target.read_bytes()
            self.assertTrue(install_claude(home,script,True)['dryRun'])
            self.assertEqual(target.read_bytes(),before)
            result=install_claude(home,script)
            self.assertEqual(Path(result['backup']).read_bytes(),before)
            actual=json.loads(target.read_text())
            self.assertEqual(actual['preferences'],original['preferences'])
            self.assertEqual(actual['mcpServers']['existing'],original['mcpServers']['existing'])
            self.assertFalse(install_claude(home,script)['changed'])
            other=home/'other.py';other.write_text('')
            with self.assertRaises(ValueError):install_claude(home,other)

if __name__=='__main__':unittest.main()
