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
