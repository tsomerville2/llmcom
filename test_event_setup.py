import json
from pathlib import Path
import tempfile
import unittest
from event_setup import provision

class ProvisionTests(unittest.TestCase):
    def test_private_idempotent_no_secret_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);accounts=root/'accounts.json';token=root/'token'
            preview=provision(accounts,token,'alice',['design'],True)
            self.assertFalse(preview['writes']);self.assertFalse(accounts.exists())
            result=provision(accounts,token,'alice',['design'])
            self.assertTrue(result['created'])
            self.assertNotIn(token.read_text().strip(),json.dumps(result)+accounts.read_text())
            self.assertEqual(token.stat().st_mode&0o777,0o600)
            self.assertEqual(accounts.stat().st_mode&0o777,0o600)
            self.assertFalse(provision(accounts,token,'alice',['design'])['created'])
            with self.assertRaises(ValueError):provision(accounts,token,'alice',['another'])
            provision(accounts,root/'bob-token','bob',['another'])
            self.assertEqual(set(json.loads(accounts.read_text())),{'alice','bob'})

if __name__=='__main__':unittest.main()
