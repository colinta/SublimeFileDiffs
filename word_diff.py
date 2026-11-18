import difflib
import json
import os
import re
import tempfile
from itertools import groupby

import sublime


TOKEN = re.compile(r"\w+(?:['’]\w+)*|[^\w\s]")
HEX_COLOR = re.compile(r'#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?\Z')


def diff_highlights(lines):
    """Find changed lines and word spans in a single-file unified diff."""
    line_ranges = {'-': [], '+': []}
    word_ranges = {'-': [], '+': []}
    # The first two entries from unified_diff are the file headers.
    changes = groupby(enumerate(lines[2:], 2), key=lambda entry: entry[1][0] in '-+')
    for changed, entries in changes:
        if not changed:
            continue
        block = {'-': [], '+': []}
        for row, line in entries:
            sign = line[0]
            line_ranges[sign].append((row, 0, len(line) - 1))
            block[sign].append((row, line))

        if not block['-'] or not block['+']:
            continue

        tokens = {
            sign: [(row, match) for row, line in rows for match in TOKEN.finditer(line, 1)]
            for sign, rows in block.items()
        }
        removed, added = tokens['-'], tokens['+']
        # Keep large replacements responsive. Their line tint still applies.
        if len(removed) * len(added) > 1000000:
            continue

        matcher = difflib.SequenceMatcher(
            None, [match.group() for _, match in removed],
            [match.group() for _, match in added], autojunk=False)
        for operation, old_start, old_end, new_start, new_end in matcher.get_opcodes():
            if operation == 'equal':
                continue
            for sign, group in (('-', removed[old_start:old_end]), ('+', added[new_start:new_end])):
                for row, row_tokens in groupby(group, key=lambda token: token[0]):
                    matches = [match for _, match in row_tokens]
                    word_ranges[sign].append((row, matches[0].start(), matches[-1].end()))
    return line_ranges, word_ranges


def unaccented_ranges(lines, words):
    words_by_row = {row: list(entries) for row, entries in groupby(words, key=lambda entry: entry[0])}
    for row, start, end in lines:
        for _, word_start, word_end in words_by_row.get(row, ()):
            if start < word_start:
                yield row, start, word_start
            start = word_end
        if start < end:
            yield row, start, end


def tint(background, accent, strength):
    base = bytes.fromhex(background[1:])
    color = bytes.fromhex(accent[1:])
    return '#' + ''.join('{:02x}'.format(round(a + (b - a) * strength)) for a, b in zip(base, color))


def color_override(pair, field):
    color = pair.get(field) if isinstance(pair, dict) else None
    if isinstance(color, str) and HEX_COLOR.match(color):
        return color
    return None


def palette_rules(view, overrides):
    style = view.style()
    background = style['background']
    foreground = style['foreground']
    if not isinstance(overrides, dict):
        overrides = {}

    rules = []
    for kind, marker, hue in (('deleted', 'line_diff_deleted', 'redish'), ('inserted', 'line_diff_added', 'greenish')):
        colors = view.style_for_scope('markup.' + kind + '.diff')
        candidates = (colors.get('background'), colors.get('foreground'), style.get(marker))
        accent = next((color for color in candidates if color and color not in (background, foreground)), None)
        if accent is None:
            accent = view.style_for_scope('region.' + hue).get('foreground') or foreground

        line_fill = tint(background, accent, 0.22)
        word_fill = tint(background, tint(accent, foreground, 0.18), 0.62)
        side = overrides.get(kind)
        for layer, fill in (('line', line_fill), ('word', word_fill)):
            pair = side.get(layer) if isinstance(side, dict) else None
            fill = color_override(pair, 'background') or fill
            text = color_override(pair, 'foreground')
            rules.append({
                'scope': 'filediffs.' + layer + '.' + kind,
                'background': fill,
                'foreground': text or 'color({} min-contrast({} 4.5))'.format(foreground, fill),
            })
    return rules


def active_scheme(view):
    scheme = view.settings().get('color_scheme')
    if not scheme or scheme == 'auto':
        scheme = sublime.ui_info().get('color_scheme', {}).get('resolved_value')
    return scheme


def update_scheme(scheme, rules):
    # Sublime merges schemes by file name. Add only FileDiffs scopes to the
    # chosen scheme so views using other schemes keep their colors.
    directory = os.path.join(sublime.packages_path(), __package__, 'WordDiffColors')
    path = os.path.join(directory, os.path.splitext(os.path.basename(scheme))[0] + '.sublime-color-scheme')
    content = json.dumps({'rules': rules}, sort_keys=True, indent=2) + '\n'
    if os.path.isfile(path):
        with open(path, encoding='utf-8') as current:
            if current.read() == content:
                return
    os.makedirs(directory, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=directory, suffix='.tmp', delete=False) as staged:
        staged.write(content)
    try:
        os.replace(staged.name, path)
    finally:
        if os.path.exists(staged.name):
            os.remove(staged.name)


def normalized_hex(color):
    if len(color) == 4:
        color = '#' + ''.join(c * 2 for c in color[1:])
    return color.lower()


def highlight(source, view, lines, overrides):
    scheme = active_scheme(source)
    if not isinstance(scheme, str) or not scheme.endswith(('.sublime-color-scheme', '.tmTheme')):
        return
    resources = sublime.find_resources(os.path.basename(scheme))
    if not resources or ('/' in scheme and scheme not in resources):
        return
    try:
        rules = palette_rules(source, overrides)
        update_scheme(scheme, rules)
    except (OSError, KeyError, ValueError):
        return

    view.settings().set('color_scheme', scheme)
    revision = view.change_count()

    def draw(remaining=20):
        if not view.is_valid() or view.change_count() != revision or active_scheme(view) != scheme:
            return
        # The file watcher may not have applied the overlay on the first call.
        if any(view.style_for_scope(rule['scope']).get('background') != normalized_hex(rule['background']) for rule in rules):
            if remaining:
                sublime.set_timeout(lambda: draw(remaining - 1), 50)
            return

        line_ranges, word_ranges = diff_highlights(lines)
        view.assign_syntax('Packages/' + __package__ + '/FileDiffs.sublime-syntax')
        for sign, kind in (('-', 'deleted'), ('+', 'inserted')):
            words = word_ranges[sign]
            for layer, ranges in (('line', unaccented_ranges(line_ranges[sign], words)), ('word', words)):
                regions = [
                    sublime.Region(view.text_point(row, start), view.text_point(row, end))
                    for row, start, end in ranges
                ]
                if regions:
                    scope = 'filediffs.' + layer + '.' + kind
                    view.add_regions(scope, regions, scope, flags=sublime.DRAW_NO_OUTLINE)

    draw()
