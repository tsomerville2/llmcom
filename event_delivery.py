"""Durable bounded webhook delivery; receipt is not proof of chat processing."""
import json
from mcp_events import signed_request


class Outbox:
    def __init__(self, store):
        self.store=store
        self.db=store.db
        self.db.execute('CREATE TABLE IF NOT EXISTS deliveries (subscription TEXT, event_id TEXT, channel TEXT, event TEXT, attempts INTEGER DEFAULT 0, due REAL, status TEXT, PRIMARY KEY(subscription,event_id))')
        self.db.execute('CREATE TABLE IF NOT EXISTS message_origins (message_id TEXT PRIMARY KEY, owner TEXT)')
        self.db.commit()

    def enqueue(self, channel, message_id, sender, text, timestamp):
        if not all(isinstance(value,str) and value for value in [channel,message_id,sender,text,timestamp]):
            raise ValueError('Relay event fields must be nonempty strings.')
        event={'eventId':'relay_'+message_id,'name':'message.created','timestamp':timestamp,
               'data':{'channel':channel,'message_id':message_id,'sender':sender,'text':text},'cursor':None}
        body=json.dumps(event,ensure_ascii=False)
        if len(body.encode())>262144:raise ValueError('Event exceeds delivery limit.')
        origin=self.db.execute('SELECT owner FROM message_origins WHERE message_id=?',(message_id,)).fetchone()
        with self.db:
            for sub in self.store.matching(channel):
                if origin and sub['id']==origin[0]:continue
                event['data']['subscription_id']=sub['id']
                body=json.dumps(event,ensure_ascii=False)
                if len(body.encode())>262144:raise ValueError('Event exceeds delivery limit.')
                self.db.execute('INSERT OR IGNORE INTO deliveries(subscription,event_id,channel,event,due,status) VALUES(?,?,?,?,?,?)',
                    (sub['id'],event['eventId'],channel,body,self.store.clock(),'pending'))

    def deliver_one(self):
        row=self.db.execute("SELECT subscription,event_id,channel,event,attempts FROM deliveries WHERE status='pending' AND due<=? ORDER BY due LIMIT 1",(self.store.clock(),)).fetchone()
        if not row:return False
        sub_id,event_id,channel,body,attempts=row
        active={s['id']:s for s in self.store.matching(channel)}
        status='cancelled';due=self.store.clock();attempts+=1
        if sub_id in active:
            sub=active[sub_id]
            data,headers=signed_request(sub,json.loads(body),self.store.clock())
            try:
                code,_=self.store.post(sub['url'],data,headers)
            except (OSError,TimeoutError):code=503
            except ValueError:code=400
            if 200<=code<300:status='accepted'
            elif code in [408,429] or code>=500:
                status='failed' if attempts>=6 else 'pending'
                due+=min(300,2**attempts)
            else:status='failed'
        with self.db:self.db.execute('UPDATE deliveries SET attempts=?,due=?,status=? WHERE subscription=? AND event_id=?',(attempts,due,status,sub_id,event_id))
        return True
