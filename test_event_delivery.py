import base64
import json
from pathlib import Path
import tempfile
import unittest
from mcp_events import SubscriptionStore
from event_delivery import Outbox

class DeliveryTests(unittest.TestCase):
    def test_retry_stable_ids_dedup_and_revocation(self):
        with tempfile.TemporaryDirectory() as directory:
            now=[1000];allowed=[True];codes=[503,200];seen=[]
            def post(url,body,headers):
                data=json.loads(body)
                if data.get('type')=='verification':return 200,json.dumps({'challenge':data['challenge']}).encode()
                seen.append((data,headers));return codes.pop(0),b''
            store=SubscriptionStore(Path(directory)/'events.db',lambda *a:allowed[0],post,lambda:now[0])
            params={'name':'message.created','arguments':{'channel':'design'},'delivery':{'mode':'webhook','url':'https://example.com/callback','secret':'whsec_'+base64.b64encode(b'a'*32).decode()}}
            store.subscribe('alice',params);queue=Outbox(store)
            args=('design','123','peer','hello','2026-10-05T12:00:00Z')
            queue.enqueue(*args);queue.enqueue(*args)
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM deliveries').fetchone()[0],1)
            self.assertTrue(queue.deliver_one());self.assertFalse(queue.deliver_one())
            now[0]+=5;self.assertTrue(queue.deliver_one())
            self.assertEqual(seen[0][0]['eventId'],seen[1][0]['eventId'])
            self.assertNotEqual(seen[0][1]['webhook-signature'],seen[1][1]['webhook-signature'])
            self.assertEqual(store.db.execute('SELECT status FROM deliveries').fetchone()[0],'accepted')
            queue.enqueue('design','124','peer','bye',args[-1]);allowed[0]=False
            queue.deliver_one()
            self.assertEqual(len(seen),2)
            self.assertEqual(store.db.execute("SELECT status FROM deliveries WHERE event_id='relay_124'").fetchone()[0],'cancelled')
            store.close()

if __name__=='__main__':unittest.main()
