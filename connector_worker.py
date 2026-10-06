"""One bounded request to existing local Chat tools; no network listener."""
import json
from pathlib import Path
import sys
from remote_chat import Chat
from mcp_events import SubscriptionStore


def main():
    config_path = Path(sys.argv[1])
    config = json.loads(config_path.read_text())
    owner = config['id']
    def accounts():
        current = json.loads(config_path.read_text())
        return {owner: {'channels': current['channels']}} if current['id'] == owner else {}
    store = SubscriptionStore(config_path.parent/'chat.sqlite', lambda o,c: c in accounts().get(o,{}).get('channels',[]))
    try:
        request = json.loads(sys.stdin.buffer.read(262145))
        print(json.dumps(Chat(store, accounts).reply(request, owner)), flush=True)
    finally:
        store.close()

if __name__ == '__main__':
    main()
