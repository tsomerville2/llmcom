"""MCP 2.0 event dispatch, independent of HTTP authentication and relay transport."""
from mcp_events import SubscriptionStore
from event_tools import SAY, call_tool

EVENT = {
    'name':'message.created',
    'description':'A new collaborator message in a channel this account can access.',
    'delivery':['webhook'],
    'inputSchema':{'type':'object','properties':{'channel':{'type':'string'}},'required':['channel'],'additionalProperties':False},
    'payloadSchema':{'type':'object','properties':{
        'subscription_id':{'type':'string'},'channel':{'type':'string'},'message_id':{'type':'string'},'sender':{'type':'string'},'text':{'type':'string'}},
        'required':['subscription_id','channel','message_id','sender','text'],'additionalProperties':False}
}


def dispatch(request, owner, store):
    if not owner:
        raise PermissionError('Authenticated account required.')
    if not isinstance(request,dict) or request.get('jsonrpc') != '2.0' or 'id' not in request:
        raise ValueError('Expected a JSON-RPC request.')
    method, params = request.get('method'), request.get('params',{})
    if not isinstance(params,dict):raise ValueError('Invalid parameters.')
    if method == 'server/discover':
        result = {'resultType':'complete','supportedVersions':['2026-07-28'],'capabilities':{'events':{},'tools':{}}}
    elif method == 'tools/list':
        result = {'tools':[SAY]}
    elif method == 'tools/call':
        result = call_tool(owner,params,store)
    elif method == 'events/list':
        result = {'events':[EVENT]}
    elif method == 'events/subscribe':
        result = store.subscribe(owner,params)
    elif method == 'events/unsubscribe':
        result = store.unsubscribe(owner,params)
    else:
        return {'jsonrpc':'2.0','id':request['id'],'error':{'code':-32601,'message':'Unknown method.'}}
    return {'jsonrpc':'2.0','id':request['id'],'result':result}


def reply(request, owner, store):
    identifier = request.get('id') if isinstance(request,dict) else None
    try:
        return dispatch(request,owner,store)
    except PermissionError:
        error = {'code':-32001,'message':'Account is not authorized for this channel.'}
    except (ValueError,TypeError,KeyError) as exc:
        if str(exc).startswith('CallbackEndpointError:'):
            error={'code':-32015,'message':'Callback verification failed.','data':{'reason':'challenge_failed'}}
        else:error={'code':-32602,'message':'Invalid event request.'}
    except (TimeoutError,OSError):
        error={'code':-32015,'message':'Callback connection failed.','data':{'reason':'connection_failed'}}
    return {'jsonrpc':'2.0','id':identifier,'error':error}
