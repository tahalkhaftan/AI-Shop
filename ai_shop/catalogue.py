"""Validate an explicit public-data contract; arbitrary application state is never indexed."""
from __future__ import annotations
import hashlib
import re

from .errors import AIShopError
from .urls import origin, public_url


def clean_text(value, limit, *, required=True):
    if not isinstance(value, str):
        raise AIShopError('invalid_public_data')
    value = value.strip()
    if len(value) > limit or (required and not value):
        raise AIShopError('invalid_public_data')
    return value


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', value):
        raise AIShopError('invalid_identifier')
    return value


def page_id(url):
    return 'page_' + hashlib.sha256(url.encode()).hexdigest()[:20]


def validate_snapshot(data, site_origin):
    """Return only whitelisted PUBLIC keys, excluding customer/admin/order fields."""
    site_origin = origin(site_origin)
    if not isinstance(data, dict):
        raise AIShopError('invalid_public_data')
    currency = data.get('currency', {})
    if not isinstance(currency, dict):
        raise AIShopError('invalid_currency')
    code = currency.get('code', 'IRT'); decimals = currency.get('decimals', 0)
    if not isinstance(code, str) or not re.fullmatch(r'[A-Z]{3}', code) or type(decimals) is not int or not 0 <= decimals <= 3:
        raise AIShopError('invalid_currency')
    result = {'brand': clean_text(data.get('brand', ''), 100), 'origin': site_origin,
              'currency': {'code': code, 'decimals': decimals, 'label': clean_text(currency.get('label', code), 40)},
              'categories': [], 'products': [], 'pages': [], 'public_info': {}}
    categories = data.get('categories', [])
    if not isinstance(categories, list) or len(categories) > 100:
        raise AIShopError('invalid_public_data')
    result['categories'] = [clean_text(c, 100) for c in categories]
    info = data.get('public_info', {})
    if not isinstance(info, dict):
        raise AIShopError('invalid_public_data')
    for key in ('phone', 'email', 'address', 'hours', 'shipping', 'returns', 'about', 'payment'):
        if key in info:
            result['public_info'][key] = clean_text(info[key], 1200, required=False)
    products = data.get('products', [])
    if not isinstance(products, list) or len(products) > 500:
        raise AIShopError('invalid_public_data')
    ids = set()
    for item in products:
        if not isinstance(item, dict): raise AIShopError('invalid_public_data')
        if item.get('active') is False or item.get('published') is False: continue
        ident = identifier(item.get('id'))
        if ident in ids: raise AIShopError('duplicate_identifier')
        ids.add(ident)
        variants = item.get('variants', [])
        if not isinstance(variants, list) or not 1 <= len(variants) <= 12:
            raise AIShopError('invalid_variants')
        packages = []
        for variant in variants:
            if not isinstance(variant, dict): raise AIShopError('invalid_variants')
            price = variant.get('price_minor')
            if type(price) is not int or not 0 <= price <= 10**12: raise AIShopError('invalid_price')
            packages.append({'unit': clean_text(variant.get('unit'), 100), 'price_minor': price})
        if type(item.get('available')) is not bool: raise AIShopError('invalid_availability')
        result['products'].append({'id': ident, 'name': clean_text(item.get('name'), 160),
            'url': public_url(item.get('url'), site_origin), 'category': clean_text(item.get('category', ''), 100, required=False),
            'description': clean_text(item.get('description', ''), 2000, required=False),
            'available': item['available'], 'variants': packages})
    pages = data.get('pages', [])
    if not isinstance(pages, list) or len(pages) > 100: raise AIShopError('invalid_public_data')
    seen = set()
    for item in pages:
        if not isinstance(item, dict): raise AIShopError('invalid_public_data')
        url = public_url(item.get('url'), site_origin)
        if url in seen: continue
        seen.add(url)
        result['pages'].append({'id': page_id(url), 'url': url,
            'title': clean_text(item.get('title', ''), 200, required=False),
            'text': clean_text(item.get('text', ''), 12000, required=False)})
    return result
