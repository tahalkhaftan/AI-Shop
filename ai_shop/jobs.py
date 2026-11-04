"""Bounded, in-memory generation jobs; no chat queue or disk archive."""
from __future__ import annotations
import copy
import secrets
import threading
import time
from .errors import AIShopError


class Jobs:
    def __init__(self):
        self.lock = threading.Lock()
        self.slot = threading.BoundedSemaphore(1)
        self.entries = {}

    def _prune(self):
        stamp = time.monotonic()
        self.entries = {key: value for key, value in self.entries.items()
                        if value['status'] == 'pending' or value['expires'] > stamp}

    def submit(self, site_id, answer):
        if not self.slot.acquire(blocking=False): raise AIShopError('busy', 503)
        ident = secrets.token_urlsafe(24)
        try:
            with self.lock:
                self._prune()
                if len(self.entries) >= 64: raise AIShopError('busy', 503)
                self.entries[ident] = {'site_id': site_id, 'status': 'pending', 'created': time.monotonic()}
            worker = threading.Thread(target=self._run, args=(ident, answer), daemon=True)
            worker.start()
        except Exception:
            with self.lock: self.entries.pop(ident, None)
            self.slot.release()
            raise
        return ident

    def _run(self, ident, answer):
        try:
            response = {'status': 'completed', 'result': answer()}
        except AIShopError as error:
            response = {'status': 'failed', 'error': error.code}
        except Exception:
            response = {'status': 'failed', 'error': 'generation_failed'}
        finally:
            # The callback and its request/history are released when this returns.
            with self.lock:
                self.entries[ident].update(response, expires=time.monotonic() + 600)
            self.slot.release()

    def get(self, site_id, ident):
        with self.lock:
            self._prune()
            job = self.entries.get(ident)
            if job is None or job['site_id'] != site_id: raise AIShopError('job_not_found', 404)
            if job['status'] == 'pending':
                if time.monotonic() - job['created'] > 1200:
                    return {'status': 'failed', 'error': 'generation_too_long'}
                return {'status': 'pending', 'retry_after_ms': 4000}
            return copy.deepcopy({key: value for key, value in job.items() if key not in ('site_id', 'created', 'expires')})
