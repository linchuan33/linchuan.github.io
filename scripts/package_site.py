"""Build a public-only Pages artifact, optimizing historic photos without changing originals."""
from pathlib import Path
import shutil
from PIL import Image, ImageOps
from build_gallery import PAGES

ROOT = Path(__file__).resolve().parents[1]


def package(root=ROOT):
    out = root / '_site'
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()
    for pattern in ('*.html', '*.png', '*.jpg'):
        for path in root.glob(pattern):
            shutil.copy2(path, out / path.name)
    for cat in PAGES:
        for directory in (cat, cat + '-preView'):
            for path in (root / directory).rglob('*'):
                if not path.is_file() or path.name.startswith('.'):
                    continue
                target = out / path.relative_to(root)
                target.parent.mkdir(parents=True, exist_ok=True)
                if path.suffix.lower() not in {'.jpg', '.jpeg', '.bmp', '.png', '.webp'}:
                    raise ValueError(f'Unsupported public asset {path.relative_to(root)}')
                if path.name.startswith('drive-') or path.parent.name.startswith('Drive-'):
                    shutil.copy2(path, target)
                    continue
                with Image.open(path) as source:
                    image = ImageOps.exif_transpose(source).convert('RGB')
                    edge = 960 if directory.endswith('-preView') else 2560
                    image.thumbnail((edge, edge), Image.Resampling.LANCZOS)
                    fmt = {'.bmp': 'BMP', '.png': 'PNG', '.webp': 'WEBP'}.get(path.suffix.lower(), 'JPEG')
                    image.save(target, format=fmt, **({'quality': 88, 'optimize': True} if fmt == 'JPEG' else {}))
    (out / '.nojekyll').touch()
    total = sum(p.stat().st_size for p in out.rglob('*') if p.is_file())
    if total >= 1024**3:
        raise ValueError('Published site exceeds 1 GiB; reduce gallery size before publishing')
    print(f'Public artifact: {total / 1024**2:.1f} MiB')


if __name__ == '__main__':
    package()
