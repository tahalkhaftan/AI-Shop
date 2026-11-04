import importlib.util
import json
import unittest
from ai_shop.engine import LocalEngine, ANSWER_SCHEMA


class Model:
    def __init__(self): self.calls=[]
    def tokenize(self,raw,**kwargs): return list(range(len(raw)//3))
    def create_chat_completion(self,**kwargs):
        self.calls.append(kwargs)
        properties=kwargs['response_format']['schema']['properties']
        result={'queries':['چای سیاه','چای']} if 'queries' in properties else {
            'reply_language':'en','reply':'Try [[product:target]].','product_ids':['target'],
            'available_label':'Available','unavailable_label':'Unavailable','currency_label':'dollars'}
        return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(result)}}]}


class EngineTests(unittest.TestCase):
    def test_large_catalogue_uses_llm_query_translation_and_stays_in_token_budget(self):
        engine=LocalEngine();model=Model();engine._model=model
        data={'brand':'Example','currency':{'code':'USD','decimals':2,'label':'dollars'},'public_info':{},'categories':['میوه','چای'],'pages':[],
              'products':[{'id':f'p{i}','name':'سیب سرخ','category':'میوه','description':'میوه تازه '*20,'available':True,'variants':[{'unit':'one','price_minor':100}]} for i in range(300)]}
        data['products'][-1].update(id='target',name='چای سیاه',category='چای',description='چای سیاه')
        engine.reply('Which black tea do you have?',[],data)
        self.assertEqual(len(model.calls),2)
        messages=model.calls[-1]['messages']
        self.assertEqual(messages[-1]['role'],'user')
        self.assertEqual(messages[-1]['content'],'Which black tea do you have?')
        self.assertIn('target',messages[0]['content'])
        self.assertTrue(engine._fits(model,messages,engine.max_tokens))

    def test_model_object_is_not_used_concurrently(self):
        engine=LocalEngine();engine._inference_lock.acquire()
        try:
            with self.assertRaises(Exception):engine.reply('Hi',[],{})
        finally:engine._inference_lock.release()

    @unittest.skipUnless(importlib.util.find_spec('llama_cpp'),'Optional native runtime not installed')
    def test_actual_json_grammar_compiles_without_repetition_explosion(self):
        from llama_cpp import LlamaGrammar
        self.assertIsNotNone(LlamaGrammar.from_json_schema(json.dumps(ANSWER_SCHEMA),verbose=False))


if __name__ == '__main__':unittest.main()
