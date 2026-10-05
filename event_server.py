"""Loopback-only authenticated MCP Events endpoint; HTTPS ingress is configured separately."""
import argparse
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import stat
from event_protocol import reply
from mcp_events import SubscriptionStore


def load_accounts(file):
    file = Path(file)
    if stat.S_IMODE(file.stat().st_mode) & 0o077:
        raise ValueError('Account file must be private (chmod 600).')
    accounts = json.loads(file.read_text())
    if not isinstance(accounts,dict):raise ValueError('Expected account mapping.')
    for owner, entry in accounts.items():
        if not owner or not isinstance(entry,dict) or not isinstance(entry.get('tokenSha256'),str) or len(entry['tokenSha256']) != 64:
            raise ValueError('Each account needs a tokenSha256 hash.')
        if not isinstance(entry.get('channels'),list) or not all(isinstance(c,str) for c in entry['channels']):
            raise ValueError('Each account needs an explicit channel list.')
    return accounts


def principal(authorization, accounts):
    if not authorization.startswith('Bearer '):return None
    token=authorization[7:]
    if not 32 <= len(token) <= 1024:return None
    digest=hashlib.sha256(token.encode()).hexdigest()
    for owner, entry in accounts.items():
        if hmac.compare_digest(digest,entry['tokenSha256']):return owner
    return None


def handler(accounts_file, store, dispatch=reply):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass  # Never log bearer tokens, URLs, or payloads.
        def setup(self):
            super().setup()
            self.connection.settimeout(10)
        def do_GET(self):
            self.send_error(405)  # Stateless JSON responses; no server-initiated SSE stream.
        def do_POST(self):
            if self.path != '/mcp':
                self.send_error(404);return
            try: owner=principal(self.headers.get('Authorization',''),load_accounts(accounts_file))
            except (OSError,ValueError):
                self.send_error(503);return
            if owner is None:
                self.send_response(401);self.send_header('WWW-Authenticate','Bearer');self.send_header('Content-Length','0');self.end_headers();return
            if self.headers.get('Transfer-Encoding'):
                self.send_error(400);return
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0 < length <= 262144:raise ValueError()
                request=json.loads(self.rfile.read(length))
                result=dispatch(request,owner,store)
                if result is None:
                    self.send_response(202);self.send_header('Content-Length','0');self.end_headers();return
                body=json.dumps(result).encode()
            except (ValueError,UnicodeError):
                self.send_error(400);return
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(body)))
            self.end_headers();self.wfile.write(body)
    return Handler


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--accounts-file',required=True,help='Private JSON: account -> tokenSha256 and channel allowlist. Raw tokens are not stored.')
    parser.add_argument('--state-file',required=True)
    parser.add_argument('--port',type=int,default=8790)
    parser.add_argument('--relay',action='store_true',help='Forward subscribed live relay messages to verified callbacks.')
    args=parser.parse_args(argv)
    load_accounts(args.accounts_file)
    authorize=lambda owner,channel:channel in load_accounts(args.accounts_file).get(owner,{}).get('channels',[])
    store=SubscriptionStore(args.state_file,authorize)
    server=HTTPServer(('127.0.0.1',args.port),handler(args.accounts_file,store))
    server.timeout=.25
    worker=None
    try:
        if args.relay:
            from event_worker import RelayWorker
            worker=RelayWorker(store)
        while True:
            server.handle_request()
            if worker:worker.tick()
    finally:
        if worker:worker.close()
        server.server_close();store.close()

if __name__=='__main__':main()
