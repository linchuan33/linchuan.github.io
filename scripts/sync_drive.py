"""Append-only Drive photo importer. Credentials are read from the environment only."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
import warnings

from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

ROOT = Path(__file__).resolve().parents[1]
API = 'https://www.googleapis.com/drive/v3/files'
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
MAX_BYTES = 80 * 1024 * 1024
SUPPORTED = {'.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif', '.bmp', '.tif', '.tiff'}
register_heif_opener()
warnings.simplefilter('error', Image.DecompressionBombWarning)


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False, encoding='utf-8') as out:
        json.dump(data, out, ensure_ascii=False, indent=2)
        out.write('\n')
        temp = out.name
    os.replace(temp, path)


def list_children(session, folder):
    token = None
    while True:
        params = {'q': f"'{folder}' in parents and trashed = false", 'pageSize': 1000,
                  'fields': 'nextPageToken,files(id,name,mimeType,size,md5Checksum)',
                  'orderBy': 'name', 'supportsAllDrives': 'true', 'includeItemsFromAllDrives': 'true'}
        if token:
            params['pageToken'] = token
        response = session.get(API, params=params, timeout=60)
        response.raise_for_status()
        payload = response.json()
        yield from payload.get('files', [])
        token = payload.get('nextPageToken')
        if not token:
            return


def walk(session, folder, location='', visited=None):
    visited = set() if visited is None else visited
    if folder in visited:
        return
    visited.add(folder)
    for item in list_children(session, folder):
        if item['mimeType'] == 'application/vnd.google-apps.folder':
            label = ' / '.join(x for x in (location, item['name']) if x)
            yield from walk(session, item['id'], label, visited)
        elif Path(item['name']).suffix.lower() in SUPPORTED:
            yield item, location or 'New uploads'


def download(session, file_id):
    with session.get(f'{API}/{file_id}', params={'alt': 'media'}, stream=True, timeout=120) as response:
        response.raise_for_status()
        out = io.BytesIO()
        for chunk in response.iter_content(1024 * 1024):
            out.write(chunk)
            if out.tell() > MAX_BYTES:
                raise ValueError('Photo exceeds 80 MiB download limit')
        return out.getvalue()


def save_images(raw, full, preview):
    """Apply camera orientation, flatten alpha, strip EXIF/GPS and encode JPEG."""
    with Image.open(io.BytesIO(raw)) as source:
        image = ImageOps.exif_transpose(source)
        rgba = image.convert('RGBA')
        rgb = Image.new('RGB', rgba.size, 'white')
        rgb.paste(rgba, mask=rgba.getchannel('A'))
        for path, edge, quality in [(full, 2560, 88), (preview, 960, 82)]:
            path.parent.mkdir(parents=True, exist_ok=True)
            resized = rgb.copy()
            resized.thumbnail((edge, edge), Image.Resampling.LANCZOS)
            temp = path.with_suffix('.tmp')
            resized.save(temp, format='JPEG', quality=quality, optimize=True)
            os.replace(temp, path)


def import_photos(session, config, state, root=ROOT):
    # Keep every historic record even when a source is moved, deleted or edited.
    imported = 0
    hashes = {v['source_md5'] for v in state['files'].values() if v.get('source_md5')}
    for cat, folder in config['categories'].items():
        response = session.get(f'{API}/{folder}', params={'fields': 'id,mimeType'}, timeout=60)
        response.raise_for_status()  # Missing access is a failure, never an empty successful sync.
        if response.json()['mimeType'] != 'application/vnd.google-apps.folder':
            raise ValueError(f'{cat} is not a folder')
        for item, location in walk(session, folder):
            if item['id'] in state['files']:
                continue
            if int(item.get('size', 0)) > MAX_BYTES:
                raise ValueError('Photo exceeds 80 MiB limit')
            checksum = item.get('md5Checksum')
            if checksum and checksum in hashes:
                continue
            # IDs, never uploaded filenames, determine public paths.
            key = hashlib.sha256(item['id'].encode()).hexdigest()[:24]
            sub = 'Drive-' + hashlib.sha256(location.encode()).hexdigest()[:12]
            full = Path(cat) / sub / f'{key}.jpg'
            preview = Path(f'{cat}-preView') / f'drive-{key}.jpg'
            raw = download(session, item['id'])
            if checksum and hashlib.md5(raw).hexdigest() != checksum:
                raise ValueError('Downloaded photo checksum mismatch')
            save_images(raw, root / full, root / preview)
            state['files'][item['id']] = {
                'cat': cat, 'sub': sub,
                # Labels enter legacy HTML templates; keep markup and quotes out.
                'location': re.sub(r'[<>\x00-\x1f\x7f\x22\x27`&]', '', location)[:160],
                'file': full.name, 'preview': preview.as_posix(), 'source_md5': checksum,
            }
            if checksum:
                hashes.add(checksum)
            imported += 1
    return imported


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--build-only', action='store_true', help='Regenerate HTML without Drive access')
    args = parser.parse_args()
    if not args.build_only:
        secret = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
        if not secret:
            raise SystemExit('Missing GOOGLE_SERVICE_ACCOUNT_JSON. See DRIVE_SYNC.md; no files changed.')
        credentials = service_account.Credentials.from_service_account_info(json.loads(secret), scopes=SCOPES)
        session = AuthorizedSession(credentials)
        config = json.loads((ROOT / 'data/drive-config.json').read_text())
        state = json.loads((ROOT / 'data/drive-state.json').read_text())
        count = import_photos(session, config, state)
        atomic_json(ROOT / 'data/drive-state.json', state)
        print(f'Imported {count} new photos (append-only).')
    from build_gallery import build
    build(ROOT)


if __name__ == '__main__':
    main()
