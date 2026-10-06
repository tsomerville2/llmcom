"""One bounded request to existing local Chat tools; no network listener."""
import json
import os
from pathlib import Path
import sys
import time
from datetime import datetime, timezone
from remote_chat import Chat
from mcp_events import SubscriptionStore


def audit(folder, event):
    """Local bounded metadata only: never credentials, message text or full arguments."""
    try:
        path=folder/'requests.jsonl'
        if path.exists() and path.stat().st_size>1048576:path.replace(folder/'requests.previous.jsonl')
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
        with os.fdopen(fd,'w') as f:f.write(json.dumps({'at':datetime.now(timezone.utc).isoformat(),**event})+'\n')
    except OSError:pass


def main():
    config_path = Path(sys.argv[1])
    config = json.loads(config_path.read_text())
    owner = config['id']
    def accounts():
        current = json.loads(config_path.read_text())
        return {owner: {'channels': current['channels']}} if current['id'] == owner else {}
    store = SubscriptionStore(config_path.parent/'chat.sqlite', lambda o,c: c in accounts().get(o,{}).get('channels',[]))
    started=time.monotonic()
    try:
        request = json.loads(sys.stdin.buffer.read(262145))
        params=request.get('params',{}) if isinstance(request,dict) else {}
        tool=params.get('name') if isinstance(params,dict) else None
        allowed={'llmcom_rooms','llmcom_join','llmcom_read','llmcom_wait','llmcom_say'}
        meta={'pid':os.getpid(),'tool':tool if tool in allowed else 'protocol'}
        audit(config_path.parent,{'event':'started',**meta})
        result=Chat(store, accounts).reply(request, owner)
        summary={'event':'completed',**meta,'duration_ms':round((time.monotonic()-started)*1000),'error':bool(isinstance(result,dict) and 'error' in result)}
        if tool in ('llmcom_read','llmcom_wait') and isinstance(result,dict) and 'result' in result:
            value=json.loads(result['result']['content'][0]['text'])
            summary.update({'count':len(value.get('messages',[])),'next_after':value.get('next_after'),'wait_status':value.get('wait_status')})
        audit(config_path.parent,summary)
        print(json.dumps(result), flush=True)
    finally:
        store.close()

if __name__ == '__main__':
    main()
