import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import patch

from ai_shop import Assistant, AIShopError, KnowledgeBase
from ai_shop.jobs import Jobs
from ai_shop.service import Service


class JobTests(unittest.TestCase):
    def test_slow_generation_returns_immediately_and_jobs_are_site_scoped(self):
        release=threading.Event()
        class SlowEngine:
            def reply(self,*args,**kwargs):
                release.wait(5)
                return {'reply':'Hello','product_ids':[],'available_label':'Available','unavailable_label':'Unavailable','currency_label':'USD'}
        with tempfile.TemporaryDirectory() as directory:
            kb=KnowledgeBase(Path(directory)/'kb.sqlite3')
            sites=[(name*16,Assistant(site_id=name,origin='https://'+name+'.example',knowledge=kb,engine=SlowEngine())) for name in ('alpha','beta')]
            server=Service(('127.0.0.1',0),sites);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            def request(path,body=None,token='alpha'*16):
                req=Request(f'http://127.0.0.1:{server.server_port}'+path,data=None if body is None else json.dumps(body).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
                try: response=urlopen(req,timeout=2)
                except HTTPError as error: response=error
                with response: return response.status,json.load(response)
            try:
                body={'message':'Hi','public_data':{'brand':'Example','currency':{'code':'USD','decimals':2}}}
                status,result=request('/v1/chat/jobs',body)
                self.assertEqual(status,202);ident=result['job_id']
                self.assertEqual(request('/v1/chat/jobs',body)[0],503)
                self.assertEqual(request('/v1/chat/jobs/'+ident)[1]['status'],'pending')
                self.assertEqual(request('/v1/chat/jobs/'+ident,token='beta'*16)[0],404)
                self.assertEqual(request('/v1/chat/jobs/'+ident,token='')[0],401)
                self.assertEqual(request('/healthz')[0],200)
                release.set()
                for _ in range(50):
                    status,result=request('/v1/chat/jobs/'+ident)
                    if result['status']!='pending':break
                    time.sleep(.01)
                self.assertEqual(result['status'],'completed');self.assertEqual(result['result']['reply'],'Hello')
                with patch('ai_shop.jobs.time.monotonic',return_value=time.monotonic()+601):
                    self.assertEqual(request('/v1/chat/jobs/'+ident)[0],404)
            finally:
                release.set();server.shutdown();server.server_close();thread.join()

    def test_model_failure_is_safe_and_does_not_keep_generation_slot(self):
        jobs=Jobs();done=threading.Event()
        def fail():
            done.set();raise AIShopError('not_installed',503)
        ident=jobs.submit('alpha',fail);done.wait(2)
        for _ in range(50):
            result=jobs.get('alpha',ident)
            if result['status']!='pending':break
            time.sleep(.01)
        self.assertEqual(result,{'status':'failed','error':'not_installed'})
        self.assertIsInstance(jobs.submit('alpha',lambda:{'reply':'Ready'}),str)


if __name__=='__main__':unittest.main()
