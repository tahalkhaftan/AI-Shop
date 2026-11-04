"""Optional real local-model smoke check. No production site or chat data is used."""
import json
from pathlib import Path
import resource
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ai_shop import Assistant, KnowledgeBase, get_engine

with tempfile.TemporaryDirectory() as directory:
    assistant=Assistant(site_id='check',origin='https://example.com',knowledge=KnowledgeBase(Path(directory)/'index.sqlite3'))
    assistant.sync_public_data(json.loads((Path(__file__).resolve().parents[1]/'examples/public-feed.json').read_text()))
    get_engine().load()
    history=[{'role':'user','content':'چه چایی دارید؟'},{'role':'assistant','content':'چای سیاه در بسته‌های ۲۵۰ و ۵۰۰ گرمی داریم.'}]
    start=time.perf_counter()
    result=assistant.answer('How much are two large packages of the black tea?',history)
    print(json.dumps({'reply':result['reply'],'seconds':round(time.perf_counter()-start,1)},ensure_ascii=False),flush=True)
    assert 3600 in [p['amount_minor'] for p in result['parts'] if p['type']=='price'],result
    assert any('a'<=c.lower()<='z' for p in result['parts'] if p['type']=='text' for c in p['text']),result
    print('Peak resident MiB:',round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024),flush=True)
    print('PASS: real local inference and verified 36.00 USD package total.',flush=True)
