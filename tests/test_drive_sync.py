import copy
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from PIL import Image
from sync_drive import import_photos, list_children, save_images
from build_gallery import build

ROOT = Path(__file__).resolve().parents[1]


class Response:
    def __init__(self, body):
        self.body = body
    def json(self):
        return self.body
    def raise_for_status(self):
        pass


class SyncTests(unittest.TestCase):
    def test_archived_photo_binds_existing_entry_without_duplicate(self):
        class Session:
            def get(self, *args, **kwargs):
                return Response({'mimeType': 'application/vnd.google-apps.folder'})
        item = {'id': 'archived-photo', 'name': 'moon.png', 'mimeType': 'image/png', 'md5Checksum': 'verified-compressed-hash'}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'data').mkdir()
            (root / 'data/drive-archive.json').write_text(json.dumps([{
                'cat': 'Landscape', 'sub': 'US_MI', 'drive_name': 'moon.png',
                'file': 'moon.bmp', 'md5': 'verified-compressed-hash',
            }]))
            state = {'version': 1, 'files': {}}
            with patch('sync_drive.walk', return_value=[(item, 'US_MI')]), patch('sync_drive.download') as downloader:
                self.assertEqual(import_photos(Session(), {'categories': {'Landscape': 'folder'}}, state, root), 0)
                downloader.assert_not_called()
            self.assertTrue(state['files']['archived-photo']['baseline'])
            self.assertEqual(state['files']['archived-photo']['file'], 'moon.bmp')

    def test_pagination(self):
        class Session:
            def get(self, url, params, timeout):
                if 'pageToken' not in params:
                    return Response({'files': [{'id': 'one'}], 'nextPageToken': 'page2'})
                self.token = params['pageToken']
                return Response({'files': [{'id': 'two'}]})
        session = Session()
        self.assertEqual([v['id'] for v in list_children(session, 'folder')], ['one', 'two'])
        self.assertEqual(session.token, 'page2')

    def test_import_is_append_only_and_preserves_originals(self):
        class Session:
            def get(self, *args, **kwargs):
                return Response({'mimeType': 'application/vnd.google-apps.folder'})
        config = {'categories': {'Portrait': 'folder'}}
        state = {'version': 1, 'files': {}}
        raw = io.BytesIO()
        Image.new('RGB', (24, 12), 'blue').save(raw, format='PNG')
        item = {'id': 'photo1', 'name': 'uploaded.png', 'mimeType': 'image/png'}
        with tempfile.TemporaryDirectory() as tmp, patch('sync_drive.walk', return_value=[(item, '香港')]), patch('sync_drive.download', return_value=raw.getvalue()) as downloader:
            root = Path(tmp)
            old = root / 'Portrait' / 'original.jpg'
            old.parent.mkdir()
            old.write_bytes(b'original file untouched')
            self.assertEqual(import_photos(Session(), config, state, root), 1)
            snapshot = copy.deepcopy(state)
            self.assertEqual(import_photos(Session(), config, state, root), 0)
            downloader.assert_called_once()
            self.assertEqual(state, snapshot)
            with patch('sync_drive.walk', return_value=[]):
                self.assertEqual(import_photos(Session(), config, state, root), 0)
            self.assertEqual(state, snapshot)
            record = state['files']['photo1']
            self.assertTrue((root / record['preview']).is_file())
            self.assertTrue((root / 'Portrait' / record['sub'] / record['file']).is_file())
            self.assertEqual(old.read_bytes(), b'original file untouched')

    def test_images_are_resized_oriented_and_strip_exif(self):
        raw = io.BytesIO()
        exif = Image.Exif()
        exif[274] = 6
        exif[315] = 'private camera metadata'
        Image.new('RGB', (3000, 1000), 'red').save(raw, format='JPEG', exif=exif)
        with tempfile.TemporaryDirectory() as tmp:
            full, preview = Path(tmp) / 'full.jpg', Path(tmp) / 'preview.jpg'
            save_images(raw.getvalue(), full, preview)
            with Image.open(full) as photo:
                self.assertEqual(photo.size, (853, 2560))
                self.assertFalse(photo.getexif())
            with Image.open(preview) as photo:
                self.assertEqual(photo.size, (320, 960))

    def test_new_location_counts_previews_and_repeated_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'data').mkdir()
            for path in ROOT.glob('gallery*.html'):
                shutil.copy(path, root / path.name)
            baseline = json.loads((ROOT / 'data/gallery-baseline.json').read_text())
            for g in baseline:
                for name in g['files']:
                    path = root / g['cat'] / g['sub'] / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.touch()
            record = {'cat': 'Landscape', 'sub': 'Drive-test', 'file': 'new.jpg',
                      'location': '香港', 'preview': 'Landscape-preView/drive-new.jpg'}
            new = root / 'Landscape/Drive-test/new.jpg'
            new.parent.mkdir()
            new.touch()
            (root / 'data/gallery-baseline.json').write_text(json.dumps(baseline))
            historic = {'baseline': True, 'cat': 'Landscape', 'sub': baseline[2]['sub'],
                        'file': baseline[2]['files'][0], 'source_md5': 'archive-hash'}
            (root / 'data/drive-state.json').write_text(json.dumps({'files': {'old-id': historic, 'id': record}}))
            build(root)
            before = {p.name: p.read_text() for p in root.glob('gallery*.html')}
            self.assertIn('70 photographs', before['gallery-landscape.html'])
            self.assertIn('香港', before['gallery-landscape.html'])
            self.assertIn('Landscape-preView/drive-new.jpg', before['gallery.html'])
            self.assertIn('}, 3000);', before['gallery.html'])
            build(root)
            self.assertEqual(before, {p.name: p.read_text() for p in root.glob('gallery*.html')})


if __name__ == '__main__':
    unittest.main()
