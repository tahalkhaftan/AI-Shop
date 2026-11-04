"""Local layered screening. This is risk reduction, not an absolute language guarantee."""
import re
import unicodedata

# Keep the lexicon out of replies. Extend it for the languages of your audience.
PROFANITY = frozenset(('fuck', 'fucking', 'fucker', 'motherfucker', 'shit', 'bullshit',
                      'bitch', 'cunt', 'asshole', 'کسکش', 'کیر', 'کونکش', 'جاکش', 'جنده', 'کصکش',
                      'کسمادرت', 'گاییدم', 'گهخور', 'کیرم', 'کصمادر', 'پدرسگ'))
TRANSLATION = str.maketrans({'ي': 'ی', 'ى': 'ی', 'ك': 'ک', 'ـ': '',
    'а': 'a', 'с': 'c', 'е': 'e', 'о': 'o', 'р': 'p', 'х': 'x', 'і': 'i', 'ѕ': 's'})
LEET = str.maketrans({'0': 'o', '1': 'i', '3': 'e', '4': 'a', '5': 's', '7': 't', '@': 'a', '$': 's'})
INJECTION = re.compile(r'ignore (?:all |the )?(?:previous|prior|system) instructions|reveal (?:your |the )?(?:system prompt|secret)|'
                       r'<\|(?:im_start|im_end|system)|دستور(?:های|ات) قبلی.{0,25}نادیده|افشای.{0,20}رمز', re.I)
PII = re.compile(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|(?:\+?[0-9۰-۹٠-٩][\s().-]*){8,}|'
                 r'(?:sk-|gh[pousr]_)[A-Za-z0-9_-]{12,}|(?:password|api.?key|رمز عبور|شماره حساب|کد ملی)\s*[:=]', re.I)
VOLATILE = re.compile(r'تومان|تومن|ریال|دلار|یورو|درصد تخفیف|موجودی|قیمت|price|in stock|discount|shipping (?:fee|cost)|\b(?:USD|EUR|IRT|IRR|costs?|stock|sale|dollars?)\b|[$€£¥₹]', re.I)
PERSONAL = re.compile(r'\b(?:my address|my phone|my name|i live|i suffer|من زندگی|نام من|شماره من|بیماری من|آدرس من)\b', re.I)


def normalized(text):
    text = unicodedata.normalize('NFKC', str(text)).lower().translate(TRANSLATION)
    return ''.join(c for c in text if unicodedata.category(c) not in ('Cf', 'Mn', 'Me'))


def abusive(text):
    value = normalized(text).translate(LEET)
    words = re.findall(r'[^\W_]+', value, re.UNICODE)
    words += [re.sub(r'[\W_]', '', m.group()) for m in re.finditer(r'(?<!\w)(?:[^\W\d_][\W_]+){2,}[^\W\d_](?!\w)', value)]
    return any(word in PROFANITY or word.removesuffix('s') in PROFANITY or word.removesuffix('ها') in PROFANITY or
               re.sub(r'(.)\1{2,}', r'\1', word) in PROFANITY for word in words)


def unsafe_knowledge(text):
    return abusive(text) or bool(INJECTION.search(normalized(text)))


def private_text(text):
    return bool(PII.search(normalized(text)) or PERSONAL.search(normalized(text)))


def memory_allowed(text):
    return isinstance(text, str) and 8 <= len(text.strip()) <= 600 and not (
        unsafe_knowledge(text) or private_text(text) or VOLATILE.search(normalized(text)) or any(c.isdigit() for c in text))


def respectful_reply(message):
    if re.search(r'[\u0600-\u06ff]', message):
        return 'با احترام ادامه می‌دیم. دربارهٔ محصولات یا اطلاعات عمومی سایت چه پرسشی دارید؟'
    return 'Let’s keep the conversation respectful. What would you like to know about this site or its products?'


def safe_catalogue(snapshot):
    """Do not echo abusive source labels or ingest known instruction overrides."""
    result = dict(snapshot)
    result['currency'] = dict(snapshot['currency'])
    if abusive(result['currency']['label']): result['currency']['label'] = result['currency']['code']
    result['brand'] = snapshot['brand'] if not unsafe_knowledge(snapshot['brand']) else 'Store'
    result['categories'] = [s for s in snapshot['categories'] if not unsafe_knowledge(s)]
    result['public_info'] = {k: v for k, v in snapshot['public_info'].items() if not unsafe_knowledge(v)}
    result['products'] = [p for p in snapshot['products'] if not unsafe_knowledge(' '.join(
        [p['name'], p['category'], p['description']] + [v['unit'] for v in p['variants']]))]
    result['pages'] = [p for p in snapshot['pages'] if not unsafe_knowledge(p['title'] + '\n' + p['text'])]
    return result
