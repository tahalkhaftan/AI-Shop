"""Tenant-scoped public index and consented, reviewed learning. No raw chat archive."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sqlite3
import time

from .catalogue import identifier, validate_snapshot
from .errors import AIShopError
from .safety import memory_allowed
from .urls import origin, public_url


def _normalize(value):
    return ' '.join(value.split()).casefold()


class KnowledgeBase:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as con:
            con.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS sites(site_id TEXT PRIMARY KEY, origin TEXT NOT NULL, snapshot TEXT);
                CREATE TABLE IF NOT EXISTS candidates(
                    site_id TEXT NOT NULL, id TEXT NOT NULL, question TEXT NOT NULL,
                    created INTEGER NOT NULL, expires INTEGER NOT NULL, PRIMARY KEY(site_id,id));
                CREATE TABLE IF NOT EXISTS facts(
                    site_id TEXT NOT NULL, id TEXT NOT NULL, question TEXT NOT NULL,
                    answer TEXT NOT NULL, source_url TEXT NOT NULL, expires INTEGER NOT NULL,
                    PRIMARY KEY(site_id,id));
            ''')
        self.path.chmod(0o600)
        self.prune()

    def connect(self):
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        return con

    def prune(self):
        stamp = int(time.time())
        with self.connect() as con:
            con.execute('DELETE FROM candidates WHERE expires<?', (stamp,))
            con.execute('DELETE FROM facts WHERE expires<?', (stamp,))

    def register(self, site_id, site_origin):
        identifier(site_id); site_origin = origin(site_origin)
        with self.connect() as con:
            row = con.execute('SELECT origin FROM sites WHERE site_id=?', (site_id,)).fetchone()
            if row and row['origin'] != site_origin:
                raise AIShopError('site_origin_conflict', 409)
            con.execute('INSERT OR IGNORE INTO sites(site_id,origin) VALUES(?,?)', (site_id, site_origin))

    def sync(self, site_id, snapshot):
        with self.connect() as con:
            row = con.execute('SELECT origin FROM sites WHERE site_id=?', (identifier(site_id),)).fetchone()
            if not row: raise AIShopError('unknown_site', 404)
            public = validate_snapshot(snapshot, row['origin'])
            con.execute('UPDATE sites SET snapshot=? WHERE site_id=?',
                        (json.dumps(public, ensure_ascii=False, separators=(',', ':')), site_id))
        return public

    def snapshot(self, site_id):
        with self.connect() as con:
            row = con.execute('SELECT snapshot FROM sites WHERE site_id=?', (identifier(site_id),)).fetchone()
        if not row or not row['snapshot']: raise AIShopError('site_not_indexed', 503)
        return json.loads(row['snapshot'])

    def propose(self, site_id, question, *, consent=False):
        # Consent alone is not enough: private data, volatile prices and insults
        # are rejected before writing anything, including rejected text, to disk.
        if consent is not True: return None
        if not memory_allowed(question): return None
        self.snapshot(site_id)
        stamp = int(time.time())
        question = question.strip()
        ident = hashlib.sha256((site_id + '\n' + _normalize(question)).encode()).hexdigest()[:24]
        with self.connect() as con:
            con.execute('DELETE FROM candidates WHERE expires<?', (stamp,))
            count = con.execute('SELECT COUNT(*) FROM candidates WHERE site_id=?', (site_id,)).fetchone()[0]
            if count >= 100: return None
            con.execute('INSERT OR IGNORE INTO candidates VALUES(?,?,?,?,?)', (site_id, ident, question, stamp, stamp + 7*86400))
        return ident

    def pending(self, site_id):
        self.prune()
        with self.connect() as con:
            return [dict(row) for row in con.execute(
                'SELECT id,question,created,expires FROM candidates WHERE site_id=? AND expires>? ORDER BY created',
                (identifier(site_id), int(time.time())))]

    def approve(self, site_id, candidate_id, *, excerpt, source_url):
        snapshot = self.snapshot(site_id)
        source_url = public_url(source_url, snapshot['origin'])
        if not memory_allowed(excerpt): raise AIShopError('unsafe_learning')
        page = next((p for p in snapshot['pages'] if p['url'] == source_url), None)
        if page is None or _normalize(excerpt) not in _normalize(page['text']):
            raise AIShopError('public_source_required')
        stamp = int(time.time())
        with self.connect() as con:
            row = con.execute('SELECT question FROM candidates WHERE site_id=? AND id=? AND expires>?',
                              (site_id, candidate_id, stamp)).fetchone()
            if not row: raise AIShopError('unknown_candidate', 404)
            con.execute('INSERT OR REPLACE INTO facts VALUES(?,?,?,?,?,?)',
                        (site_id, candidate_id, row['question'], excerpt.strip(), source_url, stamp + 30*86400))
            con.execute('DELETE FROM candidates WHERE site_id=? AND id=?', (site_id, candidate_id))

    def facts(self, site_id):
        self.prune()
        snapshot = self.snapshot(site_id)
        pages = {p['url']: _normalize(p['text']) for p in snapshot['pages']}
        with self.connect() as con:
            rows = con.execute('SELECT id,question,answer,source_url FROM facts WHERE site_id=? AND expires>?',
                               (site_id, int(time.time()))).fetchall()
        # A removed or changed public source invalidates a learned answer immediately.
        return [dict(row) for row in rows if memory_allowed(row['question']) and memory_allowed(row['answer']) and
                _normalize(row['answer']) in pages.get(row['source_url'], '')]

    def forget(self, site_id):
        identifier(site_id)
        with self.connect() as con:
            con.execute('DELETE FROM candidates WHERE site_id=?', (site_id,))
            con.execute('DELETE FROM facts WHERE site_id=?', (site_id,))
