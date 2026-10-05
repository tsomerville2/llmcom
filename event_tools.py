"""Authorized, retry-aware channel replies for the event endpoint."""
import json
import re
from desktop_mcp import runtime

SAY = {'name':'llmcom_say','description':'Send an authorized reply to a channel through the desktop bridge identity. Reuse request_id for retries of the same message.',
       'inputSchema':{'type':'object','properties':{'channel':{'type':'string'},'text':{'type':'string'},'request_id':{'type':'string'},'subscription_id':{'type':'string','description':'When replying to an event, copy its subscription_id to suppress only this chat echo.'}},
                      'required':['channel','text','request_id'],'additionalProperties':False},
       'annotations':{'readOnlyHint':False,'destructiveHint':False,'idempotentHint':True,'openWorldHint':True}}


def call_tool(owner,params,store,send=runtime):
    if params.get('name') != 'llmcom_say':raise ValueError('Unknown tool.')
    args=params.get('arguments',{})
    if not isinstance(args,dict) or not {'channel','text','request_id'} <= set(args) or set(args)-{'channel','text','request_id','subscription_id'}:raise ValueError('Invalid arguments.')
    channel,text,key=args['channel'],args['text'],args['request_id']
    if not isinstance(channel,str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}',channel):raise ValueError('Invalid channel.')
    if not isinstance(text,str) or not 1<=len(text)<=16000:raise ValueError('Invalid text.')
    if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,128}',key):raise ValueError('Invalid request_id.')
    if not store.authorize(owner,channel):raise PermissionError('Channel access denied.')
    origin=args.get('subscription_id')
    if origin is not None:
        row=store.db.execute('SELECT owner,channel FROM subscriptions WHERE id=?',(origin,)).fetchone()
        if row!=(owner,channel):raise PermissionError('Subscription does not belong to this account and channel.')
    db=store.db
    db.execute('CREATE TABLE IF NOT EXISTS outgoing (owner TEXT, request_id TEXT, channel TEXT, text TEXT, result TEXT, PRIMARY KEY(owner,request_id))')
    previous=db.execute('SELECT channel,text,result FROM outgoing WHERE owner=? AND request_id=?',(owner,key)).fetchone()
    if previous:
        if previous[:2]!=(channel,text):raise ValueError('Request key was already used for another message.')
        if previous[2] is None:
            return {'isError':True,'content':[{'type':'text','text':'Previous send outcome is uncertain. Check channel history before sending again; automatic retry was suppressed.'}]}
        result=json.loads(previous[2])
    else:
        with db:db.execute('INSERT INTO outgoing VALUES(?,?,?,?,NULL)',(owner,key,channel,text))
        # Persist before sending. A crash in the send/commit window is uncertain,
        # never grounds to blindly send the message again.
        result=send('post',channel,text)
        with db:
            db.execute('UPDATE outgoing SET result=? WHERE owner=? AND request_id=?',(json.dumps(result),owner,key))
            db.execute('CREATE TABLE IF NOT EXISTS message_origins (message_id TEXT PRIMARY KEY, owner TEXT)')
            if isinstance(result,dict) and result.get('id'):
                db.execute('INSERT OR REPLACE INTO message_origins VALUES (?,?)',(str(result['id']),origin))
    return {'content':[{'type':'text','text':json.dumps(result)}]}
