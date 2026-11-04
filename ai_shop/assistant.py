"""Site-specific orchestration, verified references and privacy-preserving learning."""
from __future__ import annotations
import json
import re
import unicodedata

from .catalogue import clean_text
from .engine import get_engine
from .errors import AIShopError
from .knowledge import KnowledgeBase
from .safety import abusive, safe_catalogue, respectful_reply, private_text
from .urls import origin as site_origin


def validate_conversation(message, history):
    message = clean_text(message, 1000)
    if not isinstance(history, list) or len(history) > 12: raise AIShopError('invalid_history')
    clean = []
    for entry in history:
        if not isinstance(entry, dict) or entry.get('role') not in ('user', 'assistant'):
            raise AIShopError('invalid_history')
        content = clean_text(entry.get('content'), 1400)
        if not abusive(content): clean.append({'role': entry['role'], 'content': content})
    return message, clean


def _unit_matches(value, variants):
    def normalized(text):
        chars=[]
        for char in unicodedata.normalize('NFKC', text).casefold():
            if unicodedata.category(char) in ('Cf','Mn','Me'): continue
            if char.isdecimal(): char=str(unicodedata.decimal(char))
            chars.append(char if char.isalnum() else ' ')
        return ''.join(chars)
    value=normalized(value);matches=set()
    for index,variant in enumerate(variants):
        compact=''.join(normalized(variant['unit']).split())
        if len(compact)<3 and not (len(compact)>=2 and any(c.isdigit() for c in compact)): continue
        pattern=r'(?<!\w)'+r'\s*'.join(re.escape(c) for c in compact)+r'(?!\w)'
        if re.search(pattern,value): matches.add(index)
    return matches


def resolve_answer(answer, catalogue, *, message=''):
    """Never trust model-generated URLs, product names, price arithmetic or HTML."""
    try:
        reply = clean_text(answer.get('reply'), 2400)
        labels = {field: clean_text(answer.get(field), 50) for field in ('available_label', 'unavailable_label', 'currency_label')}
        locale=str(answer.get('reply_language','')).casefold()
        persian=locale in ('fa','fa-ir','persian','فارسی')
        fallbacks={'available_label':'موجود' if persian else 'Available',
                   'unavailable_label':'ناموجود' if persian else 'Unavailable',
                   'currency_label':catalogue['currency']['label']}
        for field,value in labels.items():
            if not any(char.isalpha() for char in value): labels[field]=fallbacks[field]
        ids = answer.get('product_ids')
        if not isinstance(ids, list) or len(ids) > 8 or not all(isinstance(i, str) for i in ids):
            raise AIShopError('invalid_model_output', 503)
        by_id = {p['id']: p for p in catalogue['products']}
        pages = {p['id']: p for p in catalogue['pages']}
        parts = []; referenced = []; end = 0
        pattern = re.compile(r'\[\[(product|price|total|page):([A-Za-z0-9_-]{1,80})(?::([0-9]{1,2}))?(?::([0-9]{1,2}))?\]\]')
        for match in pattern.finditer(reply):
            prefix = reply[end:match.start()]
            if '[[' in prefix or ']]' in prefix: raise AIShopError('invalid_model_reference', 503)
            if prefix: parts.append({'type': 'text', 'text': prefix})
            kind, ident, index, quantity = match.groups()
            if kind == 'page':
                if ident not in pages or index is not None or quantity is not None:
                    raise AIShopError('invalid_model_reference', 503)
                page = pages[ident]
                parts.append({'type': 'page', 'id': ident, 'text': page['title'] or page['url'], 'url': page['url']})
            else:
                if ident not in by_id: raise AIShopError('invalid_model_reference', 503)
                product = by_id[ident]; referenced.append(ident)
                if kind == 'product':
                    if index is not None or quantity is not None: raise AIShopError('invalid_model_reference', 503)
                    parts.append({'type': 'product', 'id': ident, 'text': product['name'], 'url': product['url']})
                else:
                    if index is None or int(index) >= len(product['variants']): raise AIShopError('invalid_model_reference', 503)
                    if kind == 'price' and quantity is not None: raise AIShopError('invalid_model_reference', 503)
                    if kind == 'total' and (quantity is None or not 1 <= int(quantity) <= 99): raise AIShopError('invalid_model_reference', 503)
                    selected_index=int(index)
                    requested=_unit_matches(message,product['variants'])
                    described=_unit_matches(reply,product['variants'])
                    if len(described)==1 and selected_index not in described:
                        # A uniquely named package in BOTH request and prose is
                        # authoritative over the model's mistaken numeric index.
                        # Ambiguous comparisons are not silently rewritten.
                        monetary_count=len(re.findall(r'\[\[(?:price|total):'+re.escape(ident)+r':',reply))
                        comparison=bool(re.search(r'\b(?:compare|comparison|versus|vs|cheaper|difference|or|مقایسه|فرق|یا|بین)\b',message+' '+reply,re.I))
                        if requested==described and monetary_count==1 and not comparison: selected_index=next(iter(described))
                        else: raise AIShopError('package_mismatch',503)
                    count = int(quantity) if quantity else 1
                    parts.append({'type': 'price', 'id': ident, 'variant_index': selected_index, 'quantity': count,
                                  'unit':product['variants'][selected_index]['unit'],
                                  'amount_minor': product['variants'][selected_index]['price_minor'] * count,
                                  'currency': catalogue['currency']['code'], 'decimals': catalogue['currency']['decimals']})
            end = match.end()
        tail = reply[end:]
        if '[[' in tail or ']]' in tail: raise AIShopError('invalid_model_reference', 503)
        if tail: parts.append({'type': 'text', 'text': tail})
        for position, part in enumerate(parts):
            if position and part['type'] == 'text' and parts[position - 1]['type'] == 'price':
                part['text'] = re.sub(r'^\s*' + re.escape(labels['currency_label']) + r'(?=\s|[.,؛،!?؟]|$)', '', part['text'], count=1)
        selected = []; seen = set()
        for ident in referenced + ids:
            if ident in by_id and ident not in seen:
                selected.append(by_id[ident]); seen.add(ident)
            if len(selected) >= 8: break
        plain = ''.join(p['text'] if p['type'] != 'price' else money(p['amount_minor'], p['decimals']) + ' ' + labels['currency_label'] for p in parts)
        # Check every outgoing text, including linked names and package labels.
        outgoing = ' '.join([plain, *labels.values()] + [p['name'] for p in selected] +
                            [v['unit'] for p in selected for v in p['variants']])
        if abusive(outgoing): raise AIShopError('unsafe_model_output', 503)
        return {'reply': plain, 'parts': parts, 'products': selected, 'labels': labels,
                'currency': catalogue['currency'], 'moderation': {'blocked': False}}
    except AIShopError as error:
        if error.status == 503: raise
        raise AIShopError('invalid_model_output', 503) from None
    except (KeyError, TypeError, ValueError, AttributeError):
        raise AIShopError('invalid_model_output', 503) from None


def money(amount, decimals):
    if not decimals: return f'{amount:,}'
    whole, fraction = divmod(amount, 10**decimals)
    return f'{whole:,}.{fraction:0{decimals}d}'


class Assistant:
    def __init__(self, *, site_id, origin, knowledge, engine=None):
        self.site_id = site_id
        self.origin = site_origin(origin)
        self.knowledge = knowledge
        self.engine = engine if engine is not None else get_engine()
        self.knowledge.register(site_id, self.origin)

    def sync_public_data(self, data):
        return self.knowledge.sync(self.site_id, data)

    def index_public_site(self, *, brand, currency=None, feed_url=None, max_pages=25):
        from .crawler import crawl
        return self.sync_public_data(crawl(self.origin, brand=brand, currency=currency, feed_url=feed_url, max_pages=max_pages))

    def answer(self, message, history=None, *, public_data=None, learning_consent=False):
        message, history = validate_conversation(message, [] if history is None else history)
        # Keep this request's validated prices even if another request syncs
        # the same site while generation is starting.
        snapshot = self.sync_public_data(public_data) if public_data is not None else self.knowledge.snapshot(self.site_id)
        catalogue = safe_catalogue(snapshot)
        def neutral():
            reply = respectful_reply(message)
            return {'reply': reply, 'parts': [{'type': 'text', 'text': reply}], 'products': [],
                    'labels': {'available_label': 'Available', 'unavailable_label': 'Unavailable', 'currency_label': catalogue['currency']['label']},
                    'currency': catalogue['currency'], 'moderation': {'blocked': True}, 'learning': {'saved': False}}
        if abusive(message): return neutral()
        catalogue['learned_facts'] = self.knowledge.facts(self.site_id)
        consent = learning_consent is True and not private_text(message) and not any(private_text(h['content']) for h in history)
        answer = self.engine.reply(message, history, catalogue, learning_consent=consent)
        try:
            result = resolve_answer(answer, catalogue, message=message)
        except AIShopError as error:
            if error.code == 'unsafe_model_output': return neutral()
            raise
        candidate_id = None
        if consent:
            candidate_id = self.knowledge.propose(self.site_id, answer.get('learning_candidate'), consent=True)
        result['learning'] = {'saved': bool(candidate_id), 'review_required': bool(candidate_id)}
        return result
