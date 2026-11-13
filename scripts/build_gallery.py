"""Regenerate static gallery lists, counts, filters and previews; preserve existing layout."""
import html
import json
from pathlib import Path
import re

PAGES = {'CuteAnimal': 'gallery-cuteanimal.html', 'Landscape': 'gallery-landscape.html',
         'Portrait': 'gallery-portrait.html'}


def js(value):
    return json.dumps(value, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')


def replace_data(source, groups):
    result, n = re.subn(r'const DATA = \[[\s\S]*?\];(?=\s*const ALL)', lambda _: 'const DATA = ' + js(groups) + ';', source, count=1)
    if n != 1:
        raise ValueError('Cannot locate gallery DATA')
    return result


def build(root):
    baseline = json.loads((root / 'data/gallery-baseline.json').read_text())
    state = json.loads((root / 'data/drive-state.json').read_text())
    groups = [dict(g, files=list(g['files'])) for g in baseline]
    additions = [p for p in state['files'].values() if not p.get('baseline')]
    by_key = {(g['cat'], g['sub']): g for g in groups}
    for photo in additions:
        key = (photo['cat'], photo['sub'])
        if key not in by_key:
            group = {'cat': key[0], 'sub': key[1], 'loc': photo['location'], 'files': []}
            groups.append(group)
            by_key[key] = group
        if photo['file'] not in by_key[key]['files']:
            by_key[key]['files'].append(photo['file'])
    for g in groups:
        for f in g['files']:
            if not (root / g['cat'] / g['sub'] / f).is_file():
                raise ValueError(f'Missing published photo: {g["cat"]}/{g["sub"]}/{f}')
    for cat, filename in PAGES.items():
        source = (root / filename).read_text()
        selected = [g for g in groups if g['cat'] == cat]
        source = replace_data(source, [{'sub': g['sub'], 'files': g['files']} for g in selected])
        count = sum(len(g['files']) for g in selected)
        source = re.sub(r"('h.count':\s*')\d+", lambda m: m[1] + str(count), source)
        source = re.sub(r'(data-i18n="h.count">)\d+', lambda m: m[1] + str(count), source)
        # Remove previous generated enhancement before inserting the current one.
        source = re.sub(r'\n\s*/\* DRIVE GENERATED START \*/[\s\S]*?/\* DRIVE GENERATED END \*/\n', '\n', source)
        new_groups = [g for g in selected if g['sub'].startswith('Drive-')]
        enhancement = "\n    /* DRIVE GENERATED START */\n"
        enhancement += f'    const DRIVE_LOCATIONS = {js({g["sub"]: g["loc"] for g in new_groups})};\n'
        if new_groups:
            extra_locations = ', '.join(g['loc'] for g in new_groups)
            enhancement += f'    TRANS.en[\"h.loc\"] += {js(", " + extra_locations)};\n'
            enhancement += f'    TRANS.cn[\"h.loc\"] += {js("、" + extra_locations)};\n'
        enhancement += """    Object.entries(DRIVE_LOCATIONS).forEach(([sub, label], i) => {
        SUB_LOC[sub] = {en: label, cn: label};
        const key = 'drive.location.' + i;
        TRANS.en[key] = label; TRANS.cn[key] = label;
        const button = document.createElement('button');
        button.className = 'f-btn'; button.dataset.sub = sub; button.dataset.i18n = key;
        button.textContent = label; button.onclick = () => filterSub(sub, button);
        document.querySelector('[data-sub="all"]').parentElement.appendChild(button);
    });
    /* DRIVE GENERATED END */
"""
        source = source.replace('    setLang(_lang);\n    renderGrid();', enhancement + '    setLang(_lang);\n    renderGrid();')
        (root / filename).write_text(source)
    path = root / 'gallery.html'
    source = replace_data(path.read_text(), groups)
    # Preserve all original preview slides; reserve up to four slots for latest uploads.
    def slides(match):
        cat = match[1]
        body = match[2]
        body = re.sub(r'\s*<img[^>]*data-drive-preview="true"[^>]*>', '', body)
        new = [p for p in additions if p['cat'] == cat][-4:][::-1]
        body = body.replace('mod-slide active', 'mod-slide') if new else body
        extra = ''.join('\n                    <img class="mod-slide' + (' active' if i == 0 else '') +
                        '" data-drive-preview="true" src="' + html.escape(p['preview'], quote=True) +
                        '" alt="" loading="' + ('eager' if i == 0 else 'lazy') + '">'
                        for i, p in enumerate(new))
        return f'<!-- {cat} Module -->\n            <div class="cat-module" onclick="window.location.href=\'{PAGES[cat]}\'">\n                <div class="mod-slides">' + extra + body + '\n                </div>'
    source = re.sub(r'<!-- (CuteAnimal|Landscape|Portrait) Module -->\s*<div class="cat-module"[^>]*>\s*<div class="mod-slides">([\s\S]*?)\s*</div>', slides, source)
    counts = [sum(len(g['files']) for g in groups if g['cat'] == cat) for cat in PAGES]
    locations = iter(', '.join(dict.fromkeys(g['loc'] for g in groups if g['cat'] == cat)) for cat in PAGES)
    source = re.sub(r'(<div class="mod-meta">\d+ <span data-i18n="mod.photos">photographs</span> · )[^<]*', lambda m: m[1] + html.escape(next(locations)), source)
    iterator = iter(counts)
    source = re.sub(r'(<div class="mod-meta">)\d+', lambda m: m[1] + str(next(iterator)), source)
    source = re.sub(r'\n\s*/\* DRIVE LABELS START \*/[\s\S]*?/\* DRIVE LABELS END \*/\n', '\n', source)
    labels = {g['sub']: g['loc'] for g in groups if g['sub'].startswith('Drive-')}
    enhancement = '\n        /* DRIVE LABELS START */\n'
    enhancement += f'        Object.assign(SUB_LABEL, {js(labels)});\n        Object.assign(SUB_LABEL_CN, {js(labels)});\n'
    enhancement += '        /* DRIVE LABELS END */\n'
    source = source.replace('        /* ── state ── */', enhancement + '        /* ── state ── */')
    path.write_text(source)
    print(f'Built galleries: {dict(zip(PAGES, counts))}')


if __name__ == '__main__':
    build(Path(__file__).resolve().parents[1])
