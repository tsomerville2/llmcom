import base64
import hashlib
import hmac
import socket
import unittest
from mcp_events import callback_target, signed_request, signing_key

class EventsTests(unittest.TestCase):
    def test_exact_bytes_signature(self):
        key = b'x' * 32
        sub = {'secret':'whsec_' + base64.b64encode(key).decode(), 'id':'sub_a'}
        body, headers = signed_request(sub, {'eventId':'evt_a','data':{'text':'hello é'}}, 42)
        expected = base64.b64encode(hmac.new(key, b'evt_a.42.'+body, hashlib.sha256).digest()).decode()
        self.assertEqual(headers['webhook-signature'], 'v1,'+expected)
        self.assertEqual(headers['X-MCP-Subscription-Id'], 'sub_a')

    def test_no_private_callbacks_or_redirect_primitives(self):
        def resolver(ip):
            return lambda *a, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip,443))]
        for ip in ['127.0.0.1','192.168.0.1','100.100.100.100','169.254.169.254','0.0.0.0','224.0.0.1']:
            with self.assertRaises(ValueError): callback_target('https://callback.example/a', resolver(ip))
        callback_target('https://callback.example/a', resolver('8.8.8.8'))
        for url in ['http://example.com','https://user:pass@example.com','https://example.com/#x']:
            with self.assertRaises(ValueError): callback_target(url, resolver('8.8.8.8'))
        for secret in ['bad','whsec_!!!','whsec_'+base64.b64encode(b'x').decode()]:
            with self.assertRaises(ValueError): signing_key(secret)


class SubscriptionTests(unittest.TestCase):
    def test_verified_persistent_scoped_idempotent_and_revoked(self):
        import json
        import tempfile
        from pathlib import Path
        from mcp_events import SubscriptionStore
        now = [1000]
        allowed = [True]
        def echo(url, body, headers):
            return 200, json.dumps({'challenge':json.loads(body)['challenge']}).encode()
        params = {'name':'message.created','arguments':{'channel':'design'},
                  'delivery':{'mode':'webhook','url':'https://callback.example/a','secret':'whsec_'+base64.b64encode(b'x'*32).decode()},'ttlMs':5000}
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory)/'subscriptions.sqlite'
            factory = lambda: SubscriptionStore(file, lambda owner, channel: allowed[0] and owner=='alice' and channel=='design', echo, lambda:now[0])
            store = factory()
            first = store.subscribe('alice', params)
            self.assertEqual(first['id'], store.subscribe('alice',params)['id'])
            self.assertEqual(len(store.matching('design')),1)
            self.assertEqual(store.matching('another'),[])
            with self.assertRaises(PermissionError): store.subscribe('bob',params)
            store.unsubscribe('bob',params)
            store.close()
            store = factory()
            self.assertEqual(len(store.matching('design')),1)
            self.assertEqual(file.stat().st_mode & 0o777,0o600)
            allowed[0]=False
            self.assertEqual(store.matching('design'),[])
            allowed[0]=True
            store.subscribe('alice',params)
            now[0]+=6
            self.assertEqual(store.matching('design'),[])
            store.close()

    def test_bad_challenge_never_activates(self):
        import tempfile
        from pathlib import Path
        from mcp_events import SubscriptionStore
        with tempfile.TemporaryDirectory() as directory:
            store = SubscriptionStore(Path(directory)/'s.db',lambda *a:True,lambda *a:(200,b'{"challenge":"wrong"}'))
            params={'name':'message.created','arguments':{'channel':'design'},'delivery':{'mode':'webhook','url':'https://callback.example/a','secret':'whsec_'+base64.b64encode(b'x'*32).decode()}}
            with self.assertRaises(ValueError):store.subscribe('alice',params)
            self.assertEqual(store.matching('design'),[])
            store.close()

if __name__ == '__main__': unittest.main()
