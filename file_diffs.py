# coding: utf8
import os
import re
import sys

import sublime
import sublime_plugin
import difflib
import tempfile
import subprocess

from fnmatch import fnmatch
from html import escape
from itertools import accumulate
import codecs

if sublime.platform() == "windows":
    from subprocess import Popen


class FileDiffMenuCommand(sublime_plugin.TextCommand):
    def is_visible(self, **kwargs):
        return get_setting('show_context_menu', True)

    def run(self, edit, cmd=None):
        # Individual menu items.
        CLIPBOARD   = {'text': clipboard_diff_caption(self.view),  'command' : 'file_diff_clipboard'}
        SELECTIONS  = {'text': 'Diff Selections',                   'command' : 'file_diff_selections'}
        SAVED       = {'text': saved_diff_caption(self.view),      'command' : 'file_diff_saved'}
        FILE        = {'text': u'Diff file with File in Project…',  'command' : 'file_diff_file'}
        TAB         = {'text': u'Diff file with Open Tab…',         'command' : 'file_diff_tab'}
        PREVIOUS    = {'text': previous_diff_caption(self.view),    'command' : 'file_diff_previous'}

        menu_items = [CLIPBOARD, SELECTIONS, SAVED, FILE, TAB, PREVIOUS]

        non_empty_regions = len([region for region in self.view.sel() if not region.empty()])

        if non_empty_regions != 2:
            menu_items.remove(SELECTIONS)

        if non_empty_regions and non_empty_regions != 2:
            for item in menu_items:
                item['text'] = item['text'].replace('Diff file', 'Diff selection')

        if cmd is not None:
            for item in menu_items:
                item['text'] += ' (' + os.path.splitext(os.path.basename(cmd[0]))[0] + ')'

        if not (self.view.file_name() and self.view.is_dirty()):
            menu_items.remove(SAVED)

        def on_done(index):
            if index >= 0:
                self.view.run_command(menu_items[index]['command'], {'cmd': cmd})

        self.view.window().show_quick_panel([item['text'] for item in menu_items], on_done)


class FileDiffCommand(sublime_plugin.TextCommand):
    def diff_content(self, view, use_selection=True):
        content = ''

        if use_selection:
            for region in view.sel():
                if region.empty():
                    continue
                content += view.substr(region)

        if not content:
            content = view.substr(sublime.Region(0, view.size()))
        return content

    def get_buffer_line_endings(self):
        """Detect buffer line ending."""
        line_sep = self.view.line_endings()
        if line_sep == 'CR':
            return '\r'
        elif line_sep == 'Unix':
            return '\n'
        elif line_sep == 'Windows':
            return '\r\n'

        return os.linesep

    def set_line_endings(self, content, line_ending):
        """Normalize all line endings in content to specified line ending."""
        if not line_ending:
            return content
        # First normalize to LF, then convert to target
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        if line_ending != '\n':
            content = content.replace('\n', line_ending)
        return content

    def prep_content(self, ab, file_name, default_name):
        content = ab.splitlines(True)
        if file_name is None:
            file_name = default_name
        content = [line.replace("\r\n", "\n").replace("\r", "\n") for line in content]

        trim_trailing_white_space_before_diff = get_setting('trim_trailing_white_space_before_diff', False)
        if trim_trailing_white_space_before_diff:
            content = [line.rstrip() for line in content]

        return (content, file_name)

    def run_diff(self, a, b, from_file, to_file, **options):
        external_diff_tool = options.get('cmd')

        if options.get('reverse'):
            from_file, to_file = to_file, from_file
            a, b = b, a

        (from_content, from_file) = self.prep_content(a, from_file, 'from_file')
        (to_content, to_file) = self.prep_content(b, to_file, 'to_file')

        context_lines = get_setting("context_lines", 3);
        if context_lines == "full":
            context_lines = sys.maxsize

        diffs = list(difflib.unified_diff(from_content, to_content, from_file, to_file, n=context_lines))

        if not diffs:
            if options.get('saved_selection'):
                if self.set_line_endings(a, '\n') != self.set_line_endings(b, '\n'):
                    self.view.show_popup('Only ignored trailing whitespace differs in the selection')
                else:
                    self.view.show_popup('No difference in the selected text')
            else:
                self.view.show_popup('No Difference')

        else:
            external_command = external_diff_tool or get_setting('cmd')
            open_in_sublime = get_setting('open_in_sublime', not external_command)

            if external_command:
                self.diff_with_external(external_command, a, b, from_file, to_file, **options)

            if open_in_sublime:
                # fix diffs
                diffs = map(lambda line: (line and line[-1] == "\n") and line or line + "\n", diffs)
                self.diff_in_sublime(diffs)

    def diff_with_external(self, external_command, a, b, from_file=None, to_file=None, **options):
        try:
            use_disk_files = not options.get('force_temp_files', False)
            from_file_on_disk = use_disk_files and self.file_will_be_read_from_disk(from_file)
            to_file_on_disk = use_disk_files and self.file_will_be_read_from_disk(to_file)

            # If a dirty file is diffed against the copy on disk, we statically set
            # `from_file_on_disk` to True; so that the diff becomes "file to temp"
            # instead of "temp to temp".
            if use_disk_files and to_file == from_file + " (Unsaved)":
                view = self.view.window().find_open_file(from_file)
                if os.path.exists(from_file) and view and view.is_dirty():
                    from_file_on_disk = True

            files_to_remove = []

            if not from_file_on_disk:
                tmp_file = tempfile.NamedTemporaryFile(dir = sublime.packages_path(), prefix = "file-diffs-", suffix = ".temp", delete=False)
                from_file = tmp_file.name
                tmp_file.close()
                files_to_remove.append(tmp_file.name)

                with codecs.open(from_file, encoding='utf-8', mode='w+') as tmp_file:
                    a_tmp = self.set_line_endings(a, self.get_buffer_line_endings())
                    tmp_file.write(a_tmp)

            if not to_file_on_disk:
                tmp_file = tempfile.NamedTemporaryFile(dir = sublime.packages_path(), prefix = "file-diffs-", suffix = ".temp", delete=False)
                to_file = tmp_file.name
                tmp_file.close()
                files_to_remove.append(tmp_file.name)

                with codecs.open(to_file, encoding='utf-8', mode='w+') as tmp_file:
                    b_tmp = self.set_line_endings(b, self.get_buffer_line_endings())
                    tmp_file.write(b_tmp)

            trim_trailing_white_space_before_diff = get_setting('trim_trailing_white_space_before_diff', False)
            if trim_trailing_white_space_before_diff:
                def trim_trailing_white_space(file_name):
                    trim_lines = []
                    modified = False
                    with codecs.open(file_name, encoding='utf-8', mode='r') as f:
                        lines = f.readlines()
                        lines = [line.replace("\n", '').replace("\r", '') for line in lines]
                        for line in lines:
                            trim_line = line.rstrip()
                            trim_lines.append(trim_line)
                            if trim_line != line:
                                modified = True
                    if modified:
                        tmp_file = tempfile.NamedTemporaryFile(dir = sublime.packages_path(), prefix = "file-diffs-", suffix = ".temp", delete=False)
                        file_name = tmp_file.name
                        tmp_file.close()
                        files_to_remove.append(tmp_file.name)
                        with codecs.open(file_name, encoding='utf-8', mode='w+') as f:
                            f.writelines('\n'.join(trim_lines))
                    return file_name

                from_file = trim_trailing_white_space(from_file)
                to_file = trim_trailing_white_space(to_file)

            if os.path.exists(from_file):
                external_command = [c.replace('$file1', from_file) for c in external_command]
                external_command = [c.replace('$file2', to_file) for c in external_command]
                external_command = [os.path.expandvars(c) for c in external_command]
                if sublime.platform() == "windows":
                    Popen(external_command)
                else:
                    subprocess.Popen(external_command)

                apply_tempfile_changes_after_diff_tool = get_setting('apply_tempfile_changes_after_diff_tool', False)
                post_diff_tool = options.get('post_diff_tool')
                if apply_tempfile_changes_after_diff_tool and post_diff_tool is not None and (not from_file_on_disk or not to_file_on_disk):
                    if from_file_on_disk:
                        from_file = None
                    if to_file_on_disk:
                        to_file = None
                    # Use a dialog to block st and wait for the closing of the diff tool
                    if sublime.ok_cancel_dialog("Apply changes from tempfile after external diff tool execution?"):
                        post_diff_tool(from_file, to_file)
        except Exception as e:
            # some basic logging here, since we are cluttering the /tmp folder
            self.view.show_popup(str(e))

        finally:
            def remove_files():
                for file in files_to_remove:
                    os.remove(file)

            # Remove temp files after 15 seconds. We don't remove immediately,
            # because external diff tools may take some time to read them from disk.
            sublime.set_timeout_async(remove_files, 15000)

    def diff_in_sublime(self, diffs):
        global do_not_record
        do_not_record = True
        try:
            scratch = self.view.window().new_file()
            scratch.settings().set('filediffs_result', True)
            scratch.set_scratch(True)
            scratch.set_syntax_file('Packages/Diff/Diff.tmLanguage')
            scratch.run_command('file_diff_dummy1', {'content': ''.join(diffs)})
        finally:
            do_not_record = False

    def read_file(self, file_name):
        content = ''
        with codecs.open(file_name, mode='U', encoding='utf-8') as f:
            content = f.read()
        return content

    def get_file_name(self, view, default_name):
        file_name = ''
        if view.file_name():
            file_name = view.file_name()
        elif view.name():
            file_name = view.name()
        else:
            file_name = default_name
        return file_name

    def get_content_from_file(self, file_name):
        with codecs.open(file_name, encoding='utf-8', mode='r') as f:
            lines = f.readlines()
            lines = [line.replace("\r\n", "\n").replace("\r", "\n") for line in lines]
            content = ''.join(lines)
            return content

    def update_view(self, view, tmp_file, use_selection=True, selections=None):
        if tmp_file:
            non_empty_regions = selections
            if non_empty_regions is None:
                non_empty_regions = [region for region in view.sel() if not region.empty()] if use_selection else []
            nb_non_empty_regions = len(non_empty_regions)
            region = None
            if nb_non_empty_regions == 0:
                region = sublime.Region(0, view.size())
            elif nb_non_empty_regions == 1:
                region = non_empty_regions[0]
            else:
                self.view.show_popup('Cannot update multiselection')
                return
            view.run_command('file_diff_replace', {
                'start': region.begin(), 'end': region.end(),
                'content': self.get_content_from_file(tmp_file),
            })

    def file_will_be_read_from_disk(self, file):
        view = self.view.window().find_open_file(file)
        return os.path.exists(file) and not (view and view.is_dirty()) and not (view and self.view_has_a_selection(view))

    def view_has_a_selection(self, view):
        """Checks if it has exactly one non-empty selection."""
        return len(view.sel()) == 1 and not view.sel()[0].empty()


class FileDiffDummy1Command(sublime_plugin.TextCommand):
    def run(self, edit, content):
        self.view.insert(edit, 0, content)


class FileDiffReplaceCommand(sublime_plugin.TextCommand):
    def run(self, edit, start, end, content):
        self.view.replace(edit, sublime.Region(start, end), content)


class FileDiffClipboardCommand(FileDiffCommand):
    def run(self, edit, **kwargs):
        to_file = self.get_file_name(self.view, 'untitled')
        for region in self.view.sel():
            if not region.empty():
                to_file += ' (Selection)'
                break
        clipboard = sublime.get_clipboard()
        def on_post_diff_tool(from_file, to_file):
            self.update_view(self.view, to_file)
            sublime.set_clipboard(self.get_content_from_file(from_file))

        reverse = kwargs.get('reverse') or get_setting('reverse_clipboard', False)
        kwargs.update({'post_diff_tool': on_post_diff_tool, 'reverse': reverse})

        self.run_diff(clipboard, self.diff_content(self.view),
            from_file='(clipboard)',
            to_file=to_file,
            **kwargs)

    def is_visible(self):
        if not get_setting('show_context_menu', True):
            return False
        return bool(sublime.get_clipboard())

    def description(self):
        return clipboard_diff_caption(self.view)


class FileDiffSelectionsCommand(FileDiffCommand):
    def trim_indent(self, lines):
        indent = None
        for line in lines:
            # ignore blank lines
            if not line:
                continue

            new_indent = re.match('[ \t]*', line).group(0)
            # ignore lines that only consist of whitespace
            if len(new_indent) == len(line):
                continue

            if indent is None:
                indent = new_indent
            elif len(new_indent) < len(indent):
                indent = new_indent

            if not indent:
                break
        return indent

    def run(self, edit, **kwargs):
        regions = self.view.sel()
        first_selection = self.view.substr(regions[0])
        second_selection = self.view.substr(regions[1])

        # trim off indent
        indent = self.trim_indent(first_selection.splitlines())
        if indent:
            first_selection = "\n".join(line[len(indent):] for line in first_selection.splitlines())

        # trim off indent
        indent = self.trim_indent(second_selection.splitlines())
        if indent:
            second_selection = "\n".join(line[len(indent):] for line in second_selection.splitlines())

        self.run_diff(first_selection, second_selection,
            from_file='first selection',
            to_file='second selection',
            **kwargs)

    def is_visible(self):
        if not get_setting('show_context_menu', True):
            return False
        return len(self.view.sel()) > 1


SAVED_SELECTION_TOKEN = re.compile(r"\w+(?:['’]\w+)*|[^\S\r\n]+|\r\n|[\r\n]|[^\w\s]")


def selection_diff_blocks(before, after, before_start=0, after_start=0, autojunk=True):
    before_offsets = [before_start] + [before_start + offset for offset in accumulate(map(len, before))]
    after_offsets = [after_start] + [after_start + offset for offset in accumulate(map(len, after))]
    matcher = difflib.SequenceMatcher(None, before, after, autojunk=autojunk)
    return [(kind, before_offsets[a], before_offsets[b], after_offsets[c], after_offsets[d])
            for kind, a, b, c, d in matcher.get_opcodes()]


def saved_selection_text(saved, current, ranges):
    """Project current buffer ranges onto the saved text using matching lines and tokens."""
    if ranges == [(0, len(current))]:
        return saved

    blocks = selection_diff_blocks(saved.splitlines(True), current.splitlines(True))
    detailed_blocks = {}
    included_deletions = set()

    def includes_deletion(start, end, point, depth):
        if start < point < end:
            return True
        if depth:
            return False

        # A whole-line deletion has no width in the buffer. Include it when
        # the selection starts on the following full line or covers the line
        # break immediately before it. A partial text selection stays strict.
        if start == point and (point == 0 or current[point - 1] == '\n'):
            line_end = current.find('\n', point)
            return end >= (len(current) if line_end < 0 else line_end)

        if point == end and point > 0 and current[point - 1] == '\n':
            line_start = current.rfind('\n', 0, point - 1) + 1
            return start <= line_start

        if point == len(current) and current.endswith('\n') and end == point - 1:
            return start <= current.rfind('\n', 0, end) + 1
        return False

    def project(start, end, spans, depth=0):
        for block in spans:
            kind, a, b, c, d = block
            left, right = max(start, c), min(end, d)
            if kind == 'delete' and (a, b) not in included_deletions and includes_deletion(start, end, c, depth):
                included_deletions.add((a, b))
                # Keep the separator before deleted final lines when the
                # selection ends just before the buffer's final newline.
                first = a - 1 if depth == 0 and c == len(current) and end < c and saved[a - 1:a] == '\n' else a
                yield saved[first:b]
            if left >= right or kind == 'insert':
                continue
            if left == c and right == d:
                yield saved[a:b]
            elif kind == 'replace' and depth < 2:
                key = (depth, block)
                if key not in detailed_blocks:
                    before, after = saved[a:b], current[c:d]
                    if depth == 0:
                        before, after = SAVED_SELECTION_TOKEN.findall(before), SAVED_SELECTION_TOKEN.findall(after)
                    detailed_blocks[key] = selection_diff_blocks(before, after, a, c,
                        autojunk=len(before) * len(after) > 1000000)
                yield from project(start, end, detailed_blocks[key], depth + 1)
            else:
                # Matching text maps one-to-one. Inside an unmatched replacement,
                # project partial boundaries monotonically onto its saved span.
                first = a + (left - c) * (b - a) // (d - c)
                last = a + (right - c) * (b - a) // (d - c)
                yield saved[first:last]

    return ''.join(part for start, end in ranges for part in project(start, end, blocks))


class FileDiffSavedCommand(FileDiffCommand):
    def run(self, edit, **kwargs):
        view = self.view
        file_name = view.file_name()
        with open(file_name, encoding='utf-8') as saved_file:
            saved = saved_file.read()
        current = self.diff_content(view, use_selection=False)
        selections = [region for region in view.sel() if not region.empty()]
        from_name, to_name = file_name, file_name + ' (Unsaved)'
        revision = view.change_count()
        reverse = kwargs.get('reverse', False)

        if selections:
            ranges = [(region.begin(), region.end()) for region in selections]
            saved = saved_selection_text(saved, current, ranges)
            current = ''.join(current[start:end] for start, end in ranges)
            from_name, to_name = file_name + ' (Saved selection)', file_name + ' (Unsaved selection)'
            kwargs['force_temp_files'] = True
            kwargs['saved_selection'] = True

        def on_post_diff_tool(from_file, to_file):
            edited_file = from_file if reverse else to_file
            if edited_file and view.is_valid() and view.change_count() == revision:
                self.update_view(view, edited_file, selections=selections)

        kwargs.update({'post_diff_tool': on_post_diff_tool})
        self.run_diff(saved, current, from_file=from_name, to_file=to_name, **kwargs)

    def is_visible(self):
        if not get_setting('show_context_menu', True):
            return False
        return bool(self.view.file_name()) and self.view.is_dirty()

    def description(self):
        return saved_diff_caption(self.view)


class FileDiffFileCommand(FileDiffCommand):
    def run(self, edit, **kwargs):
        common = None
        folders = self.view.window().folders()
        files = self.find_files(folders, [])
        for folder in folders:
            if common is None:
                common = folder
            else:
                common_len = len(common)
                while folder[0:common_len] != common[0:common_len]:
                    common_len -= 1
                    common = common[0:common_len]

        my_file = self.view.file_name()
        # filter out my_file
        files = [f for f in files if f != my_file]
        # shorten names using common length
        file_picker = [f[len(common):] for f in files]

        def on_done(index):
            if index > -1:
                self.run_diff(self.diff_content(self.view), self.read_file(files[index]),
                    from_file=self.view.file_name(),
                    to_file=files[index],
                    **kwargs)
        sublime.set_timeout(lambda: self.view.window().show_quick_panel(file_picker, on_done), 1)

    def find_files(self, folders, ret=[]):
        # Cannot access these settings!!  WHY!?
        # folder_exclude_patterns = self.view.get_setting('folder_exclude_patterns')
        # file_exclude_patterns = self.view.get_setting('file_exclude_patterns')
        folder_exclude_patterns = [".svn", ".git", ".hg", "CVS"]
        file_exclude_patterns = ["*.pyc", "*.pyo", "*.exe", "*.dll", "*.obj", "*.o", "*.a", "*.lib", "*.so", "*.dylib", "*.ncb", "*.sdf", "*.suo", "*.pdb", "*.idb", ".DS_Store", "*.class", "*.psd", "*.db"]
        max_files = get_setting('limit', 1000)

        for folder in folders:
            if not os.path.isdir(folder):
                continue

            for f in os.listdir(folder):
                fullpath = os.path.join(folder, f)
                if os.path.isdir(fullpath):
                    # excluded folder?
                    if not len([True for pattern in folder_exclude_patterns if fnmatch(f, pattern)]):
                        self.find_files([fullpath], ret)
                else:
                    # excluded file?
                    if not len([True for pattern in file_exclude_patterns if fnmatch(f, pattern)]):
                        ret.append(fullpath)
                if len(ret) >= max_files:
                    self.view.show_popup('Too many files to include all of them in this list')
                    return ret
        return ret

    def is_visible(self, **kwargs):
        return get_setting('show_context_menu', True)


def open_tab_details(view, full_path, preview_lines):
    path = view.file_name()
    if path:
        location = path if full_path else os.path.dirname(path)
        home = os.path.expanduser('~')
        if not full_path and (location == home or location.startswith(home + os.sep)):
            location = '~' + location[len(home):]
        return [escape(location)]
    if preview_lines == 0:
        return []
    if view.is_loading():
        return ['Loading…']

    preview = view.substr(sublime.Region(0, min(view.size(), 4096)))
    details = []
    for line in preview.splitlines():
        line = ' '.join(line.split())
        if line:
            details.append(escape(line[:83] + '…' if len(line) > 84 else line))
            if len(details) == preview_lines:
                break
    return details or ['Empty buffer' if not view.size() else 'No text preview']


class FileDiffTabCommand(FileDiffCommand):
    def run(self, edit, **kwargs):
        source = self.view
        window = source.window()
        if window is None:
            return
        targets = [(view, view.name() or os.path.basename(view.file_name() or ''))
                   for view in window.views() if view.is_valid() and view.id() != source.id()]
        if not targets:
            return

        untitled_count = 1
        for index, (view, title) in enumerate(targets):
            if not title:
                targets[index] = (view, 'Untitled {}'.format(untitled_count))
                untitled_count += 1

        selections = [region for region in source.sel() if not region.empty()]
        source_revision = source.change_count()
        reverse = kwargs.get('reverse', False)

        def on_done(index):
            if index < 0:
                return
            target, title = targets[index]
            if not source.is_valid() or not target.is_valid():
                sublime.status_message('FileDiffs: A comparison tab was closed')
                return
            if source.is_loading() or target.is_loading():
                sublime.status_message('FileDiffs: A tab is still loading')
                return
            if source.change_count() != source_revision:
                sublime.status_message('FileDiffs: The source tab changed')
                return

            target_revision = target.change_count()
            source_text = ''.join(source.substr(region) for region in selections) if selections else self.diff_content(source, use_selection=False)

            def on_post_diff_tool(from_file, to_file):
                source_file, target_file = (to_file, from_file) if reverse else (from_file, to_file)
                if source.is_valid() and source.change_count() == source_revision:
                    self.update_view(source, source_file, selections=selections)
                if target.is_valid() and target.change_count() == target_revision:
                    self.update_view(target, target_file, use_selection=False)

            kwargs['post_diff_tool'] = on_post_diff_tool
            if selections:
                kwargs['force_temp_files'] = True
            self.run_diff(source_text, self.diff_content(target, use_selection=False),
                from_file=self.get_file_name(source, 'Untitled'),
                to_file=target.file_name() or title,
                **kwargs)

        if len(targets) == 1:
            on_done(0)
        else:
            full_path = get_setting('expand_full_file_name_in_tab', False)
            preview_lines = get_setting('open_tab_preview_lines', 1)
            if type(preview_lines) is not int or preview_lines < 0:
                preview_lines = 1
            rows = [(title, open_tab_details(view, full_path, preview_lines)) for view, title in targets]
            if hasattr(sublime, 'QuickPanelItem'):
                items = [sublime.QuickPanelItem(title, details=details) for title, details in rows]
            else:
                items = [[title] + details for title, details in rows]
            panel_options = {}
            if int(sublime.version()) >= 4081:
                panel_options['placeholder'] = ('Compare selection with an open tab' if selections
                                                else 'Compare with an open tab')
            sublime.set_timeout(lambda: window.show_quick_panel(items, on_done, **panel_options), 1)

    def is_visible(self):
        if not get_setting('show_context_menu', True):
            return False
        window = self.view.window()
        return window is not None and len(window.views()) > 1


tab_history = {}
do_not_record = False

class FileDiffPreviousCommand(FileDiffCommand):
    def run(self, edit, **kwargs):
        current = self.view
        previous = previous_tab(current)
        record_current_view(current)
        if previous is None:
            sublime.status_message('FileDiffs: No previous tab in this window')
            return
        if current.is_loading() or previous.is_loading():
            sublime.status_message('FileDiffs: A tab is still loading')
            return

        use_selection = use_previous_selections(previous, current)

        def on_post_diff_tool(from_file, to_file):
            if previous.is_valid():
                self.update_view(previous, from_file, use_selection)
            if current.is_valid():
                self.update_view(current, to_file, use_selection)

        kwargs.update({'post_diff_tool': on_post_diff_tool})
        self.run_diff(self.diff_content(previous, use_selection), self.diff_content(current, use_selection),
            from_file=self.get_file_name(previous, 'untitled (Previous)'),
            to_file=self.get_file_name(current, 'untitled (Current)'),
            **kwargs)

    def is_visible(self):
        return get_setting('show_context_menu', True)

    def is_enabled(self):
        return previous_tab(self.view) is not None

    def description(self):
        return previous_diff_caption(self.view)


def has_selection(view):
    return any(not region.empty() for region in view.sel())


def use_previous_selections(previous, current):
    return not get_setting('ignore_unpaired_selection', False) or has_selection(previous) == has_selection(current)


def selection_diff_caption(view, caption, other, reverse=False):
    if not get_setting('show_diff_menu_details', False) or not has_selection(view):
        return caption
    left, right = ('selection', other) if reverse else (other, 'selection')
    return '{} · {} → {}'.format(caption, left, right)


def clipboard_diff_caption(view):
    return selection_diff_caption(view, 'Diff with Clipboard', 'clipboard', get_setting('reverse_clipboard', False))


def saved_diff_caption(view):
    return selection_diff_caption(view, 'Diff with Saved', 'saved selection')


def previous_diff_caption(view):
    if not get_setting('show_diff_menu_details', False):
        return 'Diff with Previous'
    previous = previous_tab(view)
    if previous is None:
        return 'Diff with Previous · no previous tab'

    pair = (previous, view)
    use_selection = use_previous_selections(*pair)
    paths = [tab.file_name() for tab in pair]
    labels = [os.path.basename(path) if path else tab.name() or 'Untitled' for tab, path in zip(pair, paths)]
    if labels[0] == labels[1]:
        labels = [path or label for path, label in zip(paths, labels)]
        if labels[0] == labels[1]:
            positions = [view.window().get_view_index(tab) for tab in pair]
            labels = ['{} (group {}, tab {})'.format(label, group + 1, index + 1)
                      for label, (group, index) in zip(labels, positions)]

    for index, tab in enumerate(pair):
        if tab.is_loading():
            labels[index] += ' (loading)'
        elif use_selection and has_selection(tab):
            labels[index] += ' (selection)'
        elif tab.size() == 0:
            labels[index] += ' (empty)'
    caption = 'Diff with Previous · {} → {}'.format(*labels)
    return caption if use_selection else caption + ' (whole files)'


def editor_tabs(window):
    return {view.id(): view for view in window.views()
            if view.is_valid() and not view.settings().get('filediffs_result')}


def previous_tab(view):
    window = view.window()
    if window is None:
        return None
    tabs = editor_tabs(window)
    current_id = view.id()
    if current_id not in tabs:
        return None
    for tab_id in tab_history.get(window.id(), ()):
        if tab_id != current_id and tab_id in tabs:
            return tabs[tab_id]
    # Immediately after loading the plugin, the only other tab is unambiguous.
    if len(tabs) == 2:
        return next(tab for tab_id, tab in tabs.items() if tab_id != current_id)
    return None


def record_current_view(view):
    if do_not_record or view is None:
        return
    window = view.window()
    if window is None:
        return
    window_id = window.id()
    view_id = view.id()
    history = tab_history.get(window_id, [])
    if history and history[0] == view_id:
        return
    tabs = editor_tabs(window)
    if view_id in tabs:
        tab_history[window_id] = [view_id] + [tab_id for tab_id in history if tab_id != view_id and tab_id in tabs]


def plugin_loaded():
    for window in sublime.windows():
        record_current_view(window.active_view())


class FileDiffListener(sublime_plugin.EventListener):
    def on_activated(self, view):
        record_current_view(view)

    def on_deactivated(self, view):
        window = view.window()
        active = window.active_view() if window is not None else None
        if active is not None and active.id() == view.id():
            record_current_view(view)

    def on_window_command(self, window, command, args):
        record_current_view(window.active_view())

    def on_post_window_command(self, window, command, args):
        record_current_view(window.active_view())

    def on_close(self, view):
        view_id = view.id()
        for history in tab_history.values():
            if view_id in history:
                history.remove(view_id)

    def on_pre_close_window(self, window):
        tab_history.pop(window.id(), None)


def get_setting(key, default=None):
    settings = sublime.load_settings('FileDiffs.sublime-settings')
    os_specific_settings = {}
    if sublime.platform() == 'windows':
        os_specific_settings = sublime.load_settings('FileDiffs (Windows).sublime-settings')
    elif sublime.platform() == 'osx':
        os_specific_settings = sublime.load_settings('FileDiffs (OSX).sublime-settings')
    else:
        os_specific_settings = sublime.load_settings('FileDiffs (Linux).sublime-settings')
    return os_specific_settings.get(key, settings.get(key, default))
