"""Optional server-to-server adapter. Browser widgets must use their site's proxy."""
from __future__ import annotations
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import threading
import time
from urllib.parse import urlsplit

from .assistant import Assistant
from .errors import AIShopError
from .knowledge import KnowledgeBase


def load_sites(path, knowledge):
    data = json.loads(Path(path).read_text(encoding='utf-8')) if path else [{
        'site_id': os.environ.get('AI_SHOP_SITE_ID', 'default'),
        'origin': os.environ.get('AI_SHOP_SITE_ORIGIN', ''),
        'token_env': 'AI_SHOP_SITE_TOKEN',
    }]
    if not isinstance(data, list) or not 1 <= len(data) <= 50: raise AIShopError('invalid_site_configuration')
    sites = []; keys = set(); ids = set()
    for item in data:
        if not isinstance(item, dict) or not all(isinstance(item.get(k), str) and item[k] for k in ('site_id', 'origin', 'token_env')):
            raise AIShopError('invalid_site_configuration')
        key = os.environ.get(item['token_env'], '')
        if not re.fullmatch(r'[!-~]{32,256}', key) or key in keys or item['site_id'] in ids: raise AIShopError('invalid_site_configuration')
        keys.add(key); ids.add(item['site_id'])
        sites.append((key, Assistant(site_id=item['site_id'], origin=item['origin'], knowledge=knowledge)))
    return sites


class Service(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address, sites):
        super().__init__(address, Handler)
        self.sites = sites; self.rate_lock = threading.Lock(); self.rates = {}
        self.connections = threading.BoundedSemaphore(24)

    def process_request(self, request, address):
        if not self.connections.acquire(blocking=False):
            self.shutdown_request(request); return
        try: super().process_request(request, address)
        except Exception:
            self.connections.release(); raise

    def process_request_thread(self, request, address):
        try: super().process_request_thread(request, address)
        finally: self.connections.release()

    def allowance(self, site_id):
        stamp = int(time.time() // 60)
        with self.rate_lock:
            self.rates = {key: value for key, value in self.rates.items() if key[1] == stamp}
            key = (site_id, stamp)
            if self.rates.get(key, 0) >= 30: raise AIShopError('rate_limited', 429)
            self.rates[key] = self.rates.get(key, 0) + 1


class Handler(BaseHTTPRequestHandler):
    server_version = 'AI-Shop/0.2'
    def log_message(self, *args):
        # No prompt, response, Authorization header or chat history logging.
        pass

    def setup(self):
        super().setup(); self.connection.settimeout(20)

    def send(self, data, status=200):
        raw = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers(); self.wfile.write(raw)

    def do_GET(self):
        if urlsplit(self.path).path == '/healthz': self.send({'status': 'ok', 'service': 'AI-Shop'})
        else: self.send({'error': 'not_found'}, 404)

    def do_POST(self):
        try:
            authorization = self.headers.get('Authorization', '')
            supplied = authorization[7:] if authorization.startswith('Bearer ') else ''
            if not supplied.isascii(): raise AIShopError('unauthorized', 401)
            selected = None
            for key, assistant in self.server.sites:
                if hmac.compare_digest(key, supplied): selected = assistant
            if selected is None: raise AIShopError('unauthorized', 401)
            request_origin = self.headers.get('Origin')
            if request_origin and request_origin != selected.origin: raise AIShopError('foreign_origin', 403)
            path = urlsplit(self.path).path
            if path not in ('/v1/chat', '/v1/sync', '/v1/ready'): raise AIShopError('not_found', 404)
            self.server.allowance(selected.site_id)
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json': raise AIShopError('json_required', 415)
            try: size = int(self.headers.get('Content-Length', '0'))
            except ValueError: raise AIShopError('invalid_body')
            # Chat may carry the current public catalogue in the same request.
            limit = 5_000_000 if path in ('/v1/chat', '/v1/sync') else 1_000
            if not 0 < size <= limit: raise AIShopError('body_too_large', 413)
            if self.headers.get('Transfer-Encoding'): raise AIShopError('invalid_body')
            raw = self.rfile.read(size)
            if len(raw) != size: raise AIShopError('invalid_body')
            try: data = json.loads(raw)
            except (ValueError, UnicodeError): raise AIShopError('invalid_json')
            if not isinstance(data, dict): raise AIShopError('invalid_body')
            # Site identity comes solely from the server-side token mapping.
            # A caller cannot select another site_id through the request body.
            if path == '/v1/ready':
                selected.engine.load()
                result = {'ready': True, 'service': 'AI-Shop', 'protocol': 1,
                          'origin': selected.origin, 'capabilities': ['chat_public_data']}
            elif path == '/v1/sync':
                if data.get('origin', selected.origin) != selected.origin: raise AIShopError('foreign_origin', 403)
                snapshot = selected.sync_public_data(data)
                result = {'indexed': True, 'products': len(snapshot['products']), 'pages': len(snapshot['pages'])}
            else:
                if 'public_data' in data and not isinstance(data['public_data'], dict): raise AIShopError('invalid_snapshot')
                if 'public_data' in data and data['public_data'].get('origin', selected.origin) != selected.origin: raise AIShopError('foreign_origin', 403)
                result = selected.answer(data.get('message'), data.get('history', []),
                                         public_data=data.get('public_data'), learning_consent=data.get('learning_consent') is True)
            self.send(result)
        except AIShopError as error: self.send({'error': error.code}, error.status)
        except (BrokenPipeError, ConnectionResetError): pass
        except Exception: self.send({'error': 'service_error'}, 500)


def serve(config=None, *, host='127.0.0.1', port=8090, data_dir='private', preload=False):
    knowledge = KnowledgeBase(Path(data_dir) / 'knowledge.sqlite3')
    sites = load_sites(config, knowledge)
    if preload:
        for _, assistant in sites: assistant.engine.load()
    server = Service((host, port), sites)
    print(f'AI-Shop listening on {host}:{port}. Use a TLS reverse proxy for public deployment.', flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
