import json
from pathlib import Path
import tempfile
import unittest
from remote_chat import Chat
from mcp_events import SubscriptionStore

class RemoteTests(unittest.TestCase):
    def test_account_isolation_paging_and_retry(self):
        with tempfile.TemporaryDirectory() as d:
            accounts={'alice':{'channels':['room']},'bob':{'channels':['room']}}
            store=SubscriptionStore(Path(d)/'state.db',lambda o,c:c in accounts.get(o,{}).get('channels',[]))
            calls=[]
            def runtime(*args):
                calls.append(args)
                if args[0]=='post':return {'id':'900','sent':True}
                before=int(args[3]) if args[3] else 206
                return [{'id':str(i),'text':'hello','agentName':'peer'} for i in range(min(205,before-1),max(0,min(205,before-1)-int(args[2])),-1)]
            chat=Chat(store,lambda:accounts,runtime)
            def call(name,args,owner='alice'):
                result=chat.reply({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':name,'arguments':args}},owner)
                return result
            joined=call('llmcom_join',{'name':'voice','channel':'room'})
            cid=json.loads(joined['result']['content'][0]['text'])['conversation_id']
            self.assertIn('error',call('llmcom_read',{'channel':'room','conversation_id':cid},'bob'))
            r=call('llmcom_read',{'channel':'room','conversation_id':cid,'after':'10','limit':3})
            self.assertEqual([m['id'] for m in json.loads(r['result']['content'][0]['text'])['messages']],['11','12','13'])
            args={'channel':'room','conversation_id':cid,'text':'hello','request_id':'one-request'}
            self.assertEqual(call('llmcom_say',args),call('llmcom_say',args))
            self.assertEqual(sum(c[0]=='post' for c in calls),1)
            accounts['alice']['channels']=[]
            self.assertIn('error',call('llmcom_read',{'channel':'room','conversation_id':cid}))
            store.close()
    def test_handshake_and_notifications(self):
        with tempfile.TemporaryDirectory() as d:
            store=SubscriptionStore(Path(d)/'state.db',lambda o,c:False)
            chat=Chat(store,lambda:{})
            response=chat.reply({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-03-26'}},'alice')
            self.assertEqual(response['result']['protocolVersion'],'2025-03-26')
            self.assertIsNone(chat.reply({'jsonrpc':'2.0','method':'notifications/initialized'},'alice'))
            self.assertIn('error',chat.reply([], 'alice'))
            store.close()
    def test_wait_arrival_timeout_and_revocation(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            allowed=True
            store=SubscriptionStore(Path(d)/'state.db',lambda o,c:allowed)
            calls=[]
            def runtime(*args):
                calls.append(args)
                return [] if len(calls)==1 else [{'id':'11','text':'wake'}]
            chat=Chat(store,lambda:{'alice':{'channels':['room']}},runtime)
            def tool(name,args):return chat.dispatch({'jsonrpc':'2.0','method':'tools/call','params':{'name':name,'arguments':args}},'alice')
            cid=json.loads(tool('llmcom_join',{'name':'voice','channel':'room'})['content'][0]['text'])['conversation_id']
            args={'conversation_id':cid,'channel':'room','after':'10','timeout_seconds':1}
            with patch('remote_chat.time.sleep'):
                value=json.loads(tool('llmcom_wait',args)['content'][0]['text'])
            self.assertEqual(value['wait_status'],'messages');self.assertFalse(value['listening']);self.assertEqual(value['messages'][0]['id'],'11')
            chat.call=lambda *args:[]
            with patch('remote_chat.time.monotonic',side_effect=[0,2]):
                value=json.loads(tool('llmcom_wait',args)['content'][0]['text'])
            self.assertEqual(value['wait_status'],'timeout');self.assertEqual(value['next_after'],'10')
            def revoke(*unused):
                nonlocal allowed
                allowed=False
            with patch('remote_chat.time.sleep',side_effect=revoke):
                with self.assertRaises(PermissionError):tool('llmcom_wait',args)
            store.close()
