import json
from pathlib import Path
import tempfile
import unittest
from discovery import discover, invitation

class DiscoveryTests(unittest.TestCase):
    def test_portable_invite_excludes_secrets_and_preserves_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'stack.json').write_text(json.dumps({'sshHost':'private-alias','workspace':'other-team','role':'alice','relayPort':8877,'baseUrl':'http://127.0.0.1:9999','apiKey':'SECRET'}))
            (root/'workspace.json').write_text(json.dumps({'workspaceId':'ws-example','apiKey':'SECRET-WORKSPACE'}))
            (root/'sessions').mkdir()
            (root/'sessions/a.json').write_text(json.dumps({'name':'alice-chat','vendor':'claude','channels':['design']}))
            info = discover(root, 'a', lambda host: 'hostname 192.168.1.42\nuser owner\nport 2222\nidentityfile /secret/key\n')
            text = invitation(info, 'design')
            self.assertIn('--workspace other-team', text)
            self.assertIn('--relay-port 8877', text)
            self.assertIn('Port 2222', text)
            self.assertIn('ws-example', text)
            self.assertNotIn('SECRET-WORKSPACE', text)
            self.assertNotIn('SECRET', json.dumps(info)+text)
            self.assertNotIn('/secret/key', json.dumps(info)+text)
            self.assertNotIn('private-alias', text)
            with self.assertRaises(ValueError): invitation(info, 'not-joined')
            info['relay']['requiresJumpHost'] = True
            with self.assertRaises(ValueError): invitation(info, 'design')

if __name__ == '__main__': unittest.main()

class ConnectionCheckTests(unittest.TestCase):
    def test_authentication_failure_is_actionable_and_redacted(self):
        from discovery import check_connection
        from types import SimpleNamespace
        info={'relay':{'sshAlias':'relay-alias','localForwardPort':None}}
        calls=[]
        def run(args,**kwargs):
            calls.append(args)
            return SimpleNamespace(returncode=255,stderr='Permission denied (publickey). PRIVATE-MARKER /private/key')
        value=check_connection(info,run)
        self.assertEqual(value['ssh']['reason'],'authorization')
        self.assertNotIn('PRIVATE-MARKER',json.dumps(value))
        self.assertIn('StrictHostKeyChecking=yes',calls[0])
        self.assertEqual(value['nativeChatDelivery'],'Not tested by this command.')
