#!/usr/bin/env python3
"""Download pinned public weights once. No inference, messages or API keys here."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
MODEL = json.loads((ROOT / 'resources/model.json').read_text())


def digest(path):
    checksum = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b''):
            checksum.update(chunk)
    return checksum.hexdigest()


def download(destination, *, opener=urlopen):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file():
        if destination.stat().st_size == MODEL['size_bytes'] and digest(destination) == MODEL['sha256']:
            print('Model already downloaded and SHA-256 verified.', flush=True)
            return destination
        raise RuntimeError('An unverified model already exists at the destination; move it before retrying.')
    partial = destination.with_suffix(destination.suffix + '.part')
    offset = partial.stat().st_size if partial.exists() else 0
    if offset > MODEL['size_bytes']:
        raise RuntimeError('Partial download is too large. Remove the .part file before retrying.')
    if shutil.disk_usage(destination.parent).free < MODEL['size_bytes'] - offset + 64 * 1024 * 1024:
        raise RuntimeError('Not enough disk space to download the model (about 2.5 GB required).')
    if offset < MODEL['size_bytes']:
        url = ('https://huggingface.co/' + MODEL['repository'] + '/resolve/' +
               MODEL['revision'] + '/' + MODEL['filename'])
        headers = {'User-Agent': 'AI-Shop-model-download/0.1', 'Accept-Encoding': 'identity'}
        if offset:
            headers['Range'] = f'bytes={offset}-'
        with opener(Request(url, headers=headers), timeout=60) as response:
            if offset and response.status == 206:
                if not response.headers.get('Content-Range', '').startswith(f'bytes {offset}-'):
                    raise RuntimeError('Unexpected download range; the existing partial file was preserved.')
            elif response.status == 200:
                offset = 0
            else:
                raise RuntimeError('Unexpected download status; retry the download.')
            with partial.open('ab' if offset else 'wb') as target:
                progress = offset
                next_report = progress + 128 * 1024 * 1024
                while chunk := response.read(4 * 1024 * 1024):
                    progress += len(chunk)
                    if progress > MODEL['size_bytes']:
                        raise RuntimeError('Downloaded file exceeds its expected size.')
                    target.write(chunk)
                    if progress >= next_report:
                        print(f'Downloaded {progress / MODEL["size_bytes"]:.0%}', flush=True)
                        next_report = progress + 128 * 1024 * 1024
    if partial.stat().st_size != MODEL['size_bytes'] or digest(partial) != MODEL['sha256']:
        raise RuntimeError('Size or SHA-256 verification failed. Remove the .part file and retry.')
    os.replace(partial, destination)
    print(f'Model ready: {destination} (SHA-256 verified)', flush=True)
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default=str(Path.cwd() / 'models' / MODEL['filename']))
    args = parser.parse_args()
    try:
        download(args.output)
    except (OSError, RuntimeError) as error:
        raise SystemExit(f'Download not completed: {error}')
