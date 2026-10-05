import base64
import json
from pathlib import Path
import tempfile
import unittest
from event_protocol import reply
from mcp_events import SubscriptionStore

class ProtocolTests(unittest.TestCase):
    def test_full_subscription_lifecycle_and_authorization(self):
        with tempfile.TemporaryDirectory() as directory:
            store=SubscriptionStore(Path(directory)/'events.db',lambda owner, channel:owner=='alice' and channel=='design',
                lambda url,body,headers:(200,json.dumps({'challenge':json.loads(body)['challenge']}).encode()))
            def request(method,params=None,owner='alice'):
                return reply({'jsonrpc':'2.0','id':1,'method':method,'params':params or {}},owner,store)
            self.assertIn('events',request('server/discover')['result']['capabilities'])
            self.assertEqual(request('events/list')['result']['events'][0]['name'],'message.created')
            params={'name':'message.created','arguments':{'channel':'design'},'delivery':{'mode':'webhook','url':'https://callback.example/x','secret':'whsec_'+base64.b64encode(b'a'*32).decode()}}
            self.assertEqual(request('events/subscribe',params,owner='bob')['error']['code'],-32001)
            self.assertIn('id',request('events/subscribe',params)['result'])
            self.assertEqual(len(store.matching('design')),1)
            self.assertEqual(request('events/unsubscribe',params)['result'],{})
            self.assertEqual(store.matching('design'),[])
            self.assertEqual(request('events/unsubscribe',params)['result'],{})
            store.close()

if __name__=='__main__':unittest.main()
