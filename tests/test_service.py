import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from ai_shop import Assistant, KnowledgeBase
from ai_shop.service import Service


class ServiceTests(unittest.TestCase):
    def test_token_selects_site_and_body_cannot_override_it(self):
        class FakeEngine:
            def reply(self,message,history,catalogue,**kwargs):
                return {'reply':'Hello from '+catalogue['brand'],'product_ids':[],
                        'available_label':'Available','unavailable_label':'Unavailable','currency_label':'USD'}
        with tempfile.TemporaryDirectory() as directory:
            kb=KnowledgeBase(Path(directory)/'private/index.sqlite3');sites=[]
            for ident in ('alpha','beta'):
                assistant=Assistant(site_id=ident,origin='https://'+ident+'.example',knowledge=kb,engine=FakeEngine())
                assistant.sync_public_data({'brand':ident,'currency':{'code':'USD','decimals':2,'label':'dollars'}})
                sites.append((ident*12,assistant))
            server=Service(('127.0.0.1',0),sites);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base='http://127.0.0.1:'+str(server.server_port)
            def request(token='',body=None,origin=None,path='/v1/chat'):
                headers={'Content-Type':'application/json','Authorization':'Bearer '+token}
                if origin:headers['Origin']=origin
                req=Request(base+path,data=json.dumps(body or {'message':'Hello'}).encode(),headers=headers)
                try:response=urlopen(req,timeout=5)
                except HTTPError as error:response=error
                return response.status,json.loads(response.read())
            try:
                self.assertEqual(request()[0],401)
                status,result=request('alpha'*12,{'message':'Hello','site_id':'beta'})
                self.assertEqual(status,200);self.assertEqual(result['reply'],'Hello from alpha')
                self.assertEqual(request('alpha'*12,origin='https://attacker.example')[0],403)
                self.assertEqual(request('beta'*12)[1]['reply'],'Hello from beta')
            finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
