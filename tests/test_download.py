import contextlib
import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ai_shop import downloader



class Response(io.BytesIO):
    def __init__(self, raw, status=200, headers=None):
        super().__init__(raw); self.status = status; self.headers = headers or {}


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.path = Path(self.temp.name) / 'weights.gguf'
        self.raw = b'GGUF-pinned-test-weights'
        self.info = {**downloader.MODEL, 'size_bytes': len(self.raw), 'sha256': hashlib.sha256(self.raw).hexdigest()}
        self.patch = patch.object(downloader, 'MODEL', self.info); self.patch.start()
        self.output = contextlib.redirect_stdout(io.StringIO()); self.output.__enter__()

    def tearDown(self):
        self.output.__exit__(None, None, None); self.patch.stop(); self.temp.cleanup()

    def test_resume_validates_range_and_checksum_before_publishing(self):
        partial = self.path.with_suffix('.gguf.part'); partial.write_bytes(self.raw[:5])
        def opener(request, timeout):
            self.assertEqual(request.get_header('Range'), 'bytes=5-')
            self.assertIn(self.info['revision'], request.full_url)
            return Response(self.raw[5:], 206, {'Content-Range': f'bytes 5-{len(self.raw)-1}/{len(self.raw)}'})
        downloader.download(self.path, opener=opener)
        self.assertEqual(self.path.read_bytes(), self.raw); self.assertFalse(partial.exists())
        downloader.download(self.path, opener=lambda *args, **kwargs: self.fail('A verified model must not be downloaded again'))

    def test_checksum_failure_never_publishes_unverified_weights(self):
        with self.assertRaises(RuntimeError):
            downloader.download(self.path, opener=lambda *args, **kwargs: Response(b'X' * len(self.raw)))
        self.assertFalse(self.path.exists())

    def test_server_ignoring_range_restarts_instead_of_appending(self):
        self.path.with_suffix('.gguf.part').write_bytes(self.raw[:5])
        downloader.download(self.path, opener=lambda *args, **kwargs: Response(self.raw))
        self.assertEqual(self.path.read_bytes(), self.raw)


if __name__ == '__main__': unittest.main()
