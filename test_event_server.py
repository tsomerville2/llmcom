import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from event_server import load_accounts,principal

class AuthTests(unittest.TestCase):
    def test_private_hash_only_account_file(self):
        token='a'*48
        with tempfile.TemporaryDirectory() as directory:
            file=Path(directory)/'accounts.json'
            file.write_text(json.dumps({'alice':{'tokenSha256':hashlib.sha256(token.encode()).hexdigest(),'channels':['design']}}))
            file.chmod(0o600)
            accounts=load_accounts(file)
            self.assertEqual(principal('Bearer '+token,accounts),'alice')
            self.assertIsNone(principal('Bearer '+'b'*48,accounts))
            self.assertIsNone(principal('',accounts))
            file.chmod(0o644)
            with self.assertRaises(ValueError):load_accounts(file)


class HTTPTests(unittest.TestCase):
    def test_actual_authenticated_http_discovery(self):
        import socket
        import subprocess
        import sys
        import time
        import urllib.request
        import urllib.error
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);token='z'*48;file=root/'accounts.json'
            file.write_text(json.dumps({'alice':{'tokenSha256':hashlib.sha256(token.encode()).hexdigest(),'channels':['design']}}));file.chmod(0o600)
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            proc=subprocess.Popen([sys.executable,str(Path(__file__).with_name('event_server.py')),'--accounts-file',str(file),'--state-file',str(root/'s.db'),'--port',str(port)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            try:
                for _ in range(100):
                    try:
                        with socket.create_connection(('127.0.0.1',port),timeout=.1):break
                    except OSError:
                        if proc.poll() is not None:self.fail('Endpoint exited before listening')
                        time.sleep(.02)
                data=json.dumps({'jsonrpc':'2.0','id':1,'method':'server/discover'}).encode()
                req=urllib.request.Request(f'http://127.0.0.1:{port}/mcp',data,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
                with urllib.request.urlopen(req,timeout=2) as response:
                    value=json.load(response)
                self.assertIn('events',value['result']['capabilities'])
                req.remove_header('Authorization')
                with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(req,timeout=2)
                self.assertEqual(caught.exception.code,401)
            finally:
                proc.terminate();proc.communicate(timeout=3)

if __name__=='__main__':unittest.main()
