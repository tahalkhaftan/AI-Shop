"""One origin per site; account, checkout and credential-bearing URLs are excluded."""
import re
import ipaddress
from urllib.parse import urlsplit, urlunsplit, urljoin, unquote, parse_qsl, urlencode

from .errors import AIShopError

PRIVATE_SEGMENTS = {
    'admin', 'wp-admin', 'login', 'logout', 'signin', 'sign-in', 'signup', 'sign-up',
    'register', 'account', 'profile', 'cart', 'basket', 'checkout', 'orders', 'order',
    'api', 'wp-json', 'wp-login', 'private', 'auth', 'payment', 'payments', 'data', 'search', 'dashboard', 'settings',
}
SECRET_QUERY = re.compile(r'token|password|secret|auth|session|email|customer|order|key|signature|redirect|destination|callback|return|^url$|^next$', re.I)


def origin(value):
    if not isinstance(value, str) or len(value) > 500 or any(c in value for c in '\\\r\n\t'):
        raise AIShopError('invalid_origin')
    try: parsed = urlsplit(value)
    except ValueError: raise AIShopError('invalid_origin') from None
    if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password:
        raise AIShopError('invalid_origin')
    try:
        host = parsed.hostname.encode('idna').decode('ascii').lower()
        port = parsed.port
    except (ValueError, UnicodeError):
        raise AIShopError('invalid_origin') from None
    if ':' in host:
        try: ipaddress.IPv6Address(host)
        except ValueError: raise AIShopError('invalid_origin') from None
        host = '[' + host + ']'
    elif not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?', host) or '..' in host:
        raise AIShopError('invalid_origin')
    authority = host + (':' + str(port) if port and port != (443 if parsed.scheme == 'https' else 80) else '')
    return parsed.scheme + '://' + authority


def public_url(value, site_origin):
    site_origin = origin(site_origin)
    if not isinstance(value, str) or len(value) > 1500 or any(c in value for c in '\\\r\n\t'):
        raise AIShopError('invalid_public_url')
    resolved = urljoin(site_origin + '/', value)
    parsed = urlsplit(resolved)
    if origin(resolved) != site_origin:
        raise AIShopError('foreign_origin')
    decoded = unquote(unquote(parsed.path)).replace('\\', '/')
    if re.search(r'%[0-9A-Fa-f]{2}', decoded): raise AIShopError('invalid_public_url')
    segments = [s.lower() for s in decoded.split('/') if s]
    if any(s in ('.', '..') or (s.startswith('.') and s != '.well-known') or
           s.split('.')[0] in PRIVATE_SEGMENTS for s in segments):
        raise AIShopError('private_url')
    query = parse_qsl(parsed.query, keep_blank_values=True)
    if any(SECRET_QUERY.search(unquote(unquote(key))) for key, _ in query):
        raise AIShopError('credential_url')
    query = [(key, val) for key, val in query if not key.lower().startswith('utm_') and key not in ('gclid', 'fbclid')]
    return site_origin + urlunsplit(('', '', parsed.path or '/', urlencode(query), ''))
