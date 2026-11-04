import socket
import unittest
from unittest.mock import patch
from ai_shop import AIShopError
from ai_shop.crawler import crawl, public_addresses, fetch_public, PublicHTML


class CrawlerTests(unittest.TestCase):
    def test_dns_to_internal_or_metadata_addresses_is_rejected_before_connection(self):
        for address in ['127.0.0.1','10.1.2.3','169.254.169.254','::1','100.100.100.200']:
            with self.subTest(address=address), patch('socket.getaddrinfo', return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',(address,443))]):
                with self.assertRaises(AIShopError): public_addresses('example.com')

    def test_non_https_and_cross_origin_fetches_are_rejected(self):
        with self.assertRaises(AIShopError): fetch_public('http://example.com/', 'http://example.com')
        with self.assertRaises(AIShopError): fetch_public('https://elsewhere.example/', 'https://example.com')

    def test_crawler_only_reads_bounded_public_links_and_structured_prices(self):
        calls = []
        def fetcher(url, origin, **kwargs):
            calls.append(url)
            if url.endswith('/robots.txt'): return 'User-agent: *\nDisallow: /blocked', 'text/plain'
            if url.endswith('/delivery'): return '<main>Reusable packaging is available.</main>', 'text/html'
            return '''<html><head><title>Example Store</title><script>hidden private script</script>
                <script type="application/ld+json">{"@type":"Product","name":"Tea","offers":{"price":"12.50","priceCurrency":"USD","availability":"https://schema.org/InStock","url":"/products/tea"}}</script></head>
                <body><main>Public products</main><div hidden>hidden personal data</div><a href="/delivery">Delivery</a>
                <a href="/admin.html">Admin</a><a href="/blocked">Blocked</a><a href="https://other.example">External</a></body></html>''', 'text/html'
        snapshot = crawl('https://example.com', brand='Example Store', currency={'code':'USD','decimals':2,'label':'dollars'}, fetcher=fetcher)
        self.assertEqual(calls, ['https://example.com/robots.txt','https://example.com/','https://example.com/delivery'])
        self.assertEqual(snapshot['products'][0]['variants'][0]['price_minor'],1250)
        self.assertTrue(snapshot['products'][0]['available'])
        public = ' '.join(p['text'] for p in snapshot['pages'])
        self.assertNotIn('hidden personal', public); self.assertNotIn('hidden private script', public)

    def test_redirects_are_validated_before_a_second_request(self):
        class Response:
            status = 302
            def getheader(self, name, default=''): return 'https://attacker.example/' if name=='Location' else default
        class Connection:
            def __init__(self,*args): pass
            def request(self,*args,**kwargs): pass
            def getresponse(self): return Response()
            def close(self): pass
        with patch('ai_shop.crawler.public_addresses', return_value=['93.184.216.34']), patch('ai_shop.crawler.PinnedHTTPSConnection', Connection):
            with self.assertRaises(AIShopError): fetch_public('https://example.com/', 'https://example.com')


if __name__ == '__main__': unittest.main()
