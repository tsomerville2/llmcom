"""MCP Events webhook primitives for ChatGPT Work (not a UI adapter).

Callbacks are pinned to validated public IPs with hostname-verified TLS.
No redirects, local addresses, credentials in URLs, or unbounded responses.
"""
import base64
import hashlib
import hmac
import http.client
import ipaddress
import json
import socket
import ssl
import time
from urllib.parse import urlsplit


def signing_key(secret):
    if not isinstance(secret, str) or not secret.startswith('whsec_'):
        raise ValueError('Expected a whsec_ signing secret.')
    try:
        key = base64.b64decode(secret[6:], validate=True)
    except Exception:
        raise ValueError('Invalid signing secret encoding.') from None
    if not 24 <= len(key) <= 64:
        raise ValueError('Signing key must contain 24–64 bytes.')
    return key


def signed_request(subscription, event, signed_at=None):
    body = json.dumps(event, separators=(',', ':'), ensure_ascii=False).encode()
    if len(body) > 262144:
        raise ValueError('Event exceeds 256 KiB.')
    timestamp = str(int(time.time() if signed_at is None else signed_at))
    event_id = event['eventId']
    signature = base64.b64encode(hmac.new(signing_key(subscription['secret']),
        event_id.encode() + b'.' + timestamp.encode() + b'.' + body, hashlib.sha256).digest()).decode()
    signatures = 'v1,' + signature
    if subscription.get('previousSecret'):
        previous = base64.b64encode(hmac.new(signing_key(subscription['previousSecret']), event_id.encode() + b'.' + timestamp.encode() + b'.' + body, hashlib.sha256).digest()).decode()
        signatures += ' v1,' + previous
    return body, {'Content-Type': 'application/json', 'webhook-id': event_id,
        'webhook-timestamp': timestamp, 'webhook-signature': signatures,
        'X-MCP-Subscription-Id': subscription['id']}


def callback_target(url, resolver=socket.getaddrinfo):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError('Callback requires an HTTPS URL without credentials or fragment.')
    port = parsed.port or 443
    addresses = resolver(parsed.hostname, port, type=socket.SOCK_STREAM)
    if not addresses:
        raise ValueError('Callback hostname has no addresses.')
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global or ip.is_multicast or (getattr(ip, 'ipv4_mapped', None) and not ip.ipv4_mapped.is_global):
            raise ValueError('Callback must resolve only to public unicast addresses.')
    return parsed, addresses[0]


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, port, address):
        super().__init__(host, port, timeout=10, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        family, kind, protocol, _, address = self.address
        raw = socket.socket(family, kind, protocol)
        raw.settimeout(self.timeout)
        try:
            raw.connect(address)
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except Exception:
            raw.close()
            raise


def post_callback(url, body, headers):
    parsed, address = callback_target(url)
    connection = PinnedHTTPS(parsed.hostname, parsed.port or 443, address)
    try:
        connection.request('POST', (parsed.path or '/') + ('?' + parsed.query if parsed.query else ''), body, headers)
        response = connection.getresponse()
        payload = response.read(65537)
        if len(payload) > 65536:
            raise ValueError('Callback response exceeds 64 KiB.')
        return response.status, payload
    finally:
        connection.close()


class SubscriptionStore:
    """Private persistent subscriptions; caller supplies authenticated resource authorization."""
    def __init__(self, file, authorize, post=post_callback, clock=time.time):
        import os
        import sqlite3
        from pathlib import Path
        file = Path(file)
        file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(file, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(descriptor)
        os.chmod(file, 0o600)
        self.db = sqlite3.connect(file)
        self.db.execute('CREATE TABLE IF NOT EXISTS subscriptions (id TEXT PRIMARY KEY, owner TEXT, channel TEXT, url TEXT, secret TEXT, expires REAL)')
        columns = {row[1] for row in self.db.execute('PRAGMA table_info(subscriptions)')}
        for name, kind in [('previous_secret','TEXT'),('rotation_until','REAL')]:
            if name not in columns: self.db.execute('ALTER TABLE subscriptions ADD COLUMN '+name+' '+kind)
        self.db.commit()
        self.authorize, self.post, self.clock = authorize, post, clock

    @staticmethod
    def identity(owner, params):
        import re
        if not isinstance(owner, str) or not owner:
            raise ValueError('Authenticated owner required.')
        arguments = params.get('arguments', {})
        if params.get('name') != 'message.created' or set(arguments) != {'channel'}:
            raise ValueError('Expected message.created with one channel filter.')
        channel = arguments['channel']
        if not isinstance(channel, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', channel):
            raise ValueError('Invalid channel filter.')
        delivery = params.get('delivery', {})
        url = delivery.get('url')
        if delivery.get('mode') != 'webhook' or not isinstance(url, str):
            raise ValueError('Webhook delivery required.')
        identity = json.dumps([owner, url, 'message.created', arguments], sort_keys=True, separators=(',', ':'))
        return 'sub_' + hashlib.sha256(identity.encode()).hexdigest(), channel, url

    def subscribe(self, owner, params):
        import secrets
        from datetime import datetime, timezone
        identifier, channel, url = self.identity(owner, params)
        if not self.authorize(owner, channel):
            raise PermissionError('Channel access denied.')
        secret = params['delivery'].get('secret')
        signing_key(secret)
        requested = params.get('ttlMs', 3600000)
        if requested is None: requested = 3600000
        if isinstance(requested, bool) or not isinstance(requested, (int, float)) or not 0 < requested <= 86400000:
            raise ValueError('ttlMs must be positive and no more than one day.')
        challenge = secrets.token_urlsafe(32)
        # Verification uses a webhook ID header, but no application event fields.
        verification_id = 'verify_' + secrets.token_hex(16)
        body = json.dumps({'type':'verification', 'challenge':challenge}, separators=(',', ':')).encode()
        timestamp = str(int(self.clock()))
        signature = base64.b64encode(hmac.new(signing_key(secret), verification_id.encode()+b'.'+timestamp.encode()+b'.'+body, hashlib.sha256).digest()).decode()
        headers = {'Content-Type':'application/json', 'webhook-id':verification_id,
                   'webhook-timestamp':timestamp, 'webhook-signature':'v1,'+signature,
                   'X-MCP-Subscription-Id':identifier}
        status, response = self.post(url, body, headers)
        try:
            echoed = json.loads(response).get('challenge')
        except (ValueError, AttributeError): echoed = None
        if not 200 <= status < 300 or not isinstance(echoed, str) or not hmac.compare_digest(echoed, challenge):
            raise ValueError('CallbackEndpointError: challenge_failed')
        expires = self.clock() + requested / 1000
        old = self.db.execute('SELECT secret,previous_secret,rotation_until FROM subscriptions WHERE id=?',(identifier,)).fetchone()
        previous, rotation_until = (old[0], self.clock()+300) if old and old[0] != secret else ((old[1],old[2]) if old else (None,None))
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO subscriptions (id,owner,channel,url,secret,expires,previous_secret,rotation_until) VALUES (?,?,?,?,?,?,?,?)',
                (identifier, owner, channel, url, secret, expires, previous, rotation_until))
        return {'id':identifier, 'refreshBefore':datetime.fromtimestamp(expires, timezone.utc).isoformat(), 'cursor':None, 'truncated':False}

    def unsubscribe(self, owner, params):
        identifier, _, _ = self.identity(owner, params)
        with self.db: self.db.execute('DELETE FROM subscriptions WHERE id=? AND owner=?', (identifier, owner))
        return {}

    def matching(self, channel):
        rows = self.db.execute('SELECT id,owner,url,secret,expires,previous_secret,rotation_until FROM subscriptions WHERE channel=?', (channel,)).fetchall()
        active = []
        for identifier, owner, url, secret, expires, previous, rotation_until in rows:
            if expires <= self.clock() or not self.authorize(owner, channel):
                with self.db: self.db.execute('DELETE FROM subscriptions WHERE id=?', (identifier,))
            else:
                active.append({'id':identifier,'owner':owner,'url':url,'secret':secret, 'previousSecret':previous if rotation_until and rotation_until > self.clock() else None})
        return active

    def close(self):
        self.db.close()
