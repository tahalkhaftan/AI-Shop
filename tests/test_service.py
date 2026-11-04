import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import os
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from ai_shop import Assistant, KnowledgeBase, AIShopError
from ai_shop.service import Service, load_sites


class ServiceTests(unittest.TestCase):
    def test_token_selects_site_and_body_cannot_override_it(self):
        class FakeEngine:
            def load(self): return self
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
                status,result=request('alpha'*12,path='/v1/ready',body={})
                self.assertEqual(status,200);self.assertTrue(result['ready'])
                self.assertIn('chat_public_data',result['capabilities'])
                self.assertEqual(request('',path='/v1/ready')[0],401)
                status,result=request('alpha'*12,{'message':'Hello','public_data':{'brand':'Fresh alpha','currency':{'code':'USD','decimals':2}}})
                self.assertEqual(status,200);self.assertEqual(result['reply'],'Hello from Fresh alpha')
                self.assertEqual(request('beta'*12)[1]['reply'],'Hello from beta')
                self.assertEqual(request('alpha'*12,{'message':'Hello','public_data':[]})[0],400)
                self.assertEqual(request('alpha'*12,{'message':'Hello','public_data':{'brand':'Wrong','origin':'https://beta.example'}})[0],403)
                sites[0][1].engine.load=lambda: (_ for _ in ()).throw(AIShopError('not_installed',503))
                self.assertEqual(request('alpha'*12,path='/v1/ready')[0],503)
            finally:server.shutdown();server.server_close();thread.join()

    def test_environment_configuration_and_same_request_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            kb=KnowledgeBase(Path(directory)/'knowledge.sqlite3')
            with patch.dict(os.environ,{'AI_SHOP_SITE_TOKEN':'valid-private-test-token-'*2,'AI_SHOP_SITE_ORIGIN':'https://example.com','AI_SHOP_SITE_ID':'default'}):
                sites=load_sites(None,kb);self.assertEqual(len(sites),1)
                bot=sites[0][1];self.assertEqual(bot.origin,'https://example.com')
                with patch.dict(os.environ,{'AI_SHOP_SITE_TOKEN':'short'}):
                    with self.assertRaises(AIShopError):load_sites(None,kb)
            current={'brand':'Current','currency':{'code':'USD','decimals':2}}
            with patch.object(kb,'snapshot',side_effect=AssertionError('Do not reread a racing sync')),patch.object(kb,'facts',return_value=[]),patch.object(bot.engine,'reply') as reply:
                reply.return_value={'reply':'Hello','product_ids':[],'available_label':'Available','unavailable_label':'Unavailable','currency_label':'USD'}
                bot.answer('Hello',public_data=current)
                self.assertEqual(reply.call_args.args[2]['brand'],'Current')


if __name__=='__main__':unittest.main()
