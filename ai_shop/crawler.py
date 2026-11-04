"""Bounded public-site crawler; no cookies, logins, browser sessions or private IPs."""
from __future__ import annotations
from collections import deque
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from http.client import HTTPSConnection
import ipaddress
import json
import socket
import ssl
from urllib.parse import urlsplit, urljoin
from urllib.robotparser import RobotFileParser

from .catalogue import page_id, validate_snapshot
from .errors import AIShopError
from .urls import origin, public_url

USER_AGENT = 'AI-Shop/0.1 (+public-site-indexer)'


def public_addresses(host):
    try:
        records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        addresses = list(dict.fromkeys(row[4][0] for row in records))
    except OSError:
        raise AIShopError('crawl_dns_failed', 502) from None
    def allowed(address):
        parsed = ipaddress.ip_address(address)
        mapped = getattr(parsed, 'ipv4_mapped', None)
        return parsed.is_global and not parsed.is_multicast and (mapped is None or mapped.is_global)
    if not addresses or any(not allowed(address) for address in addresses):
        raise AIShopError('crawl_private_address')
    return addresses


class PinnedHTTPSConnection(HTTPSConnection):
    def __init__(self, host, address):
        super().__init__(host, port=443, timeout=15, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        # Avoid an unchecked second DNS lookup. TLS still validates the original
        # hostname and uses it for SNI; certificate verification is never disabled.
        connection = socket.create_connection((self.address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(connection, server_hostname=self.host)
        except Exception:
            connection.close()
            raise


def fetch_public(url, site_origin, *, max_bytes=1_000_000):
    for _ in range(4):
        url = public_url(url, site_origin)
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or parsed.port not in (None, 443):
            raise AIShopError('crawl_https_required')
        address = public_addresses(parsed.hostname)[0]
        connection = PinnedHTTPSConnection(parsed.hostname, address)
        try:
            path = parsed.path + ('?' + parsed.query if parsed.query else '')
            connection.request('GET', path, headers={
                'User-Agent': USER_AGENT, 'Accept': 'text/html,application/json,text/plain',
                'Accept-Encoding': 'identity', 'Connection': 'close',
            })
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                url = public_url(urljoin(url, response.getheader('Location', '')), site_origin)
                continue
            if response.status != 200: raise AIShopError('crawl_http_' + str(response.status), 502)
            if response.getheader('Content-Encoding', 'identity').lower() != 'identity':
                raise AIShopError('crawl_compression_rejected')
            raw = response.read(max_bytes + 1)
            if len(raw) > max_bytes: raise AIShopError('crawl_page_too_large')
            return raw.decode('utf-8', errors='replace'), response.getheader('Content-Type', '')
        except (OSError, ValueError, ssl.SSLError):
            raise AIShopError('crawl_connection_failed', 502) from None
        finally:
            connection.close()
    raise AIShopError('crawl_redirect_limit')


class PublicHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []; self.text = []; self.title = []; self.links = []; self.structured = []
        self.json_script = None; self.in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        hidden = bool(self.stack and self.stack[-1][1]) or tag in ('style', 'template', 'noscript', 'head')
        hidden = hidden or 'hidden' in attrs or attrs.get('aria-hidden') == 'true' or 'display:none' in attrs.get('style', '').replace(' ', '')
        if tag == 'title': self.in_title = True
        if tag == 'script':
            self.json_script = [] if attrs.get('type', '').lower() == 'application/ld+json' else None
            hidden = True
        if tag == 'a' and attrs.get('href') and not hidden: self.links.append(attrs['href'])
        if tag not in ('img', 'br', 'hr', 'meta', 'link', 'input', 'source', 'area', 'base', 'wbr', 'embed'):
            self.stack.append((tag, hidden))

    def handle_endtag(self, tag):
        if tag == 'title': self.in_title = False
        if tag == 'script' and self.json_script is not None:
            try: self.structured.append(json.loads(''.join(self.json_script)))
            except ValueError: pass
            self.json_script = None
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        if self.in_title: self.title.append(data)
        if self.json_script is not None: self.json_script.append(data)
        if not self.stack or not self.stack[-1][1]: self.text.append(data)


def _objects(value):
    if isinstance(value, list):
        for item in value: yield from _objects(item)
    elif isinstance(value, dict):
        yield value
        if '@graph' in value: yield from _objects(value['@graph'])


def structured_products(documents, page_url, site_origin, currency):
    products = []
    for document in documents:
        for item in _objects(document):
            kind = item.get('@type', [])
            if 'Product' not in ([kind] if isinstance(kind, str) else kind): continue
            offers = item.get('offers', [])
            offers = [offers] if isinstance(offers, dict) else offers
            if not isinstance(offers, list): continue
            for offer in offers[:12]:
                if not isinstance(offer, dict) or offer.get('priceCurrency') != currency['code']: continue
                try:
                    price = Decimal(str(offer['price'])) * (10 ** currency['decimals'])
                    if not price.is_finite() or price != price.to_integral_value() or not 0 <= price <= 10**12: continue
                    url = public_url(offer.get('url', item.get('url', page_url)), site_origin)
                    ident = 'web_' + page_id(url)[5:]
                    candidate = {'id': ident, 'name': item['name'], 'url': url, 'category': str(item.get('category', ''))[:100],
                        'description': str(item.get('description', ''))[:2000],
                        'available': str(offer.get('availability', '')).rstrip('/').endswith('InStock'),
                        'variants': [{'unit': str(offer.get('name') or item.get('sku') or item['name'])[:100], 'price_minor': int(price)}]}
                    products.append(candidate)
                    break
                except (KeyError, TypeError, ValueError, InvalidOperation, AIShopError):
                    continue
    return products


def crawl(site_origin, *, brand, currency=None, feed_url=None, max_pages=25, fetcher=fetch_public):
    """Owner-initiated only. JSON feed is preferred for dynamic shops and live prices."""
    site_origin = origin(site_origin)
    if not 1 <= max_pages <= 100: raise AIShopError('invalid_crawl_limit')
    currency = currency or {'code': 'IRT', 'decimals': 0, 'label': 'تومان'}
    if feed_url:
        text, media_type = fetcher(public_url(feed_url, site_origin), site_origin, max_bytes=5_000_000)
        try: return validate_snapshot(json.loads(text), site_origin)
        except ValueError: raise AIShopError('invalid_public_feed') from None
    robots = RobotFileParser()
    try:
        text, _ = fetcher(site_origin + '/robots.txt', site_origin)
        robots.parse(text.splitlines())
    except AIShopError as error:
        if error.code != 'crawl_http_404': raise
        robots.parse([])
    pending = deque([(site_origin + '/', 0)]); seen = set(); pages = []; products = {}
    while pending and len(seen) < max_pages:
        url, depth = pending.popleft()
        if url in seen: continue
        seen.add(url)
        if not robots.can_fetch(USER_AGENT, url): continue
        try:
            text, media_type = fetcher(url, site_origin)
            if 'html' not in media_type: continue
            parser = PublicHTML(); parser.feed(text)
            pages.append({'url': url, 'title': ' '.join(parser.title)[:200], 'text': ' '.join(' '.join(parser.text).split())[:12000]})
            for product in structured_products(parser.structured, url, site_origin, currency): products[product['id']] = product
            if depth < 2:
                for href in parser.links[:100]:
                    try:
                        link = public_url(urljoin(url, href), site_origin)
                        if link not in seen: pending.append((link, depth + 1))
                    except AIShopError: pass
        except AIShopError:
            if not pages: raise
    return validate_snapshot({'brand': brand, 'currency': currency, 'products': list(products.values())[:500], 'pages': pages}, site_origin)
