import tempfile
from pathlib import Path
import unittest
from mcp_events import SubscriptionStore
from event_tools import call_tool

class OutgoingTests(unittest.TestCase):
    def test_retry_dedup_conflict_access_and_uncertainty(self):
        with tempfile.TemporaryDirectory() as directory:
            store=SubscriptionStore(Path(directory)/'s.db',lambda owner,channel:owner=='alice' and channel=='design')
            calls=[]
            def send(*args):calls.append(args);return {'sent':True,'id':'msg1'}
            params={'name':'llmcom_say','arguments':{'channel':'design','text':'hello','request_id':'request-123'}}
            first=call_tool('alice',params,store,send)
            self.assertEqual(first,call_tool('alice',params,store,send));self.assertEqual(len(calls),1)
            with self.assertRaises(PermissionError):call_tool('bob',params,store,send)
            params['arguments']['text']='changed'
            with self.assertRaises(ValueError):call_tool('alice',params,store,send)
            params['arguments']['request_id']='request-456'
            def fail(*args):raise OSError('send uncertain')
            with self.assertRaises(OSError):call_tool('alice',params,store,fail)
            self.assertTrue(call_tool('alice',params,store,send)['isError'])
            self.assertEqual(len(calls),1)
            store.close()

if __name__=='__main__':unittest.main()
