# coding: utf8
import os
import re

import sublime
import sublime_plugin
import difflib
import tempfile

from fnmatch import fnmatch
import codecs

if sublime.platform() == "windows":
    from subprocess import Popen


class FileDiffMenuCommand(sublime_plugin.TextCommand):
    CLIPBOARD = 'Diff file with Clipboard'
    SELECTIONS = 'Diff Selections'
    SAVED = 'Diff file with Saved'
    FILE = u'Diff file with File in Project…'
    TAB = u'Diff file with Open Tab…'
    PREVIOUS = 'Diff file with Previous window'

    FILE_DIFFS = [CLIPBOARD, SAVED, FILE, TAB, PREVIOUS]

    def run(self, edit, cmd=None):
        menu_items = self.FILE_DIFFS[:]
        saved = self.SAVED
        non_empty_regions = [region for region in self.view.sel() if not region.empty()]
        if len(non_empty_regions) == 2:
            menu_items.insert(1, self.SELECTIONS)
        elif len(non_empty_regions):
            menu_items = [f.replace('Diff file', 'Diff selection') for f in menu_items]
            saved = saved.replace('Diff file', 'Diff selection')

        if not (self.view.file_name() and self.view.is_dirty()):
            menu_items.remove(saved)

        def on_done(index):
            restored_menu_items = [f.replace('Diff selection', 'Diff file') for f in menu_items]
            if index == -1:
                return
            elif restored_menu_items[index] == self.CLIPBOARD:
                self.view.run_command('file_diff_clipboard', {'cmd': cmd})
            elif restored_menu_items[index] == self.SELECTIONS:
                self.view.run_command('file_diff_selections', {'cmd': cmd})
            elif restored_menu_items[index] == self.SAVED:
                self.view.run_command('file_diff_saved', {'cmd': cmd})
            elif restored_menu_items[index] == self.FILE:
                self.view.run_command('file_diff_file', {'cmd': cmd})
            elif restored_menu_items[index] == self.TAB:
                self.view.run_command('file_diff_tab', {'cmd': cmd})
            elif restored_menu_items[index] == self.PREVIOUS:
                self.view.run_command('file_diff_previous', {'cmd': cmd})
        self.view.window().show_quick_panel(menu_items, on_done)


class FileDiffCommand(sublime_plugin.TextCommand):
    def settings(self):
        return sublime.load_settings('FileDiffs.sublime-settings')

    def diff_content(self):
        content = ''

        for region in self.view.sel():
            if region.empty():
                continue
            content += self.view.substr(region)

        if not content:
            content = self.view.substr(sublime.Region(0, self.view.size()))
        return content

    def prep_content(self, ab, file_name, default_name):
        content = ab.splitlines(True)
        if file_name is None:
            file_name = default_name
        content = [line.replace("\r\n", "\n").replace("\r", "\n") for line in content]

        trim_trailing_white_space_before_diff = self.settings().get('trim_trailing_white_space_before_diff', False)
        if trim_trailing_white_space_before_diff:
            content = [line.rstrip() for line in content]

        return (content, file_name)

    def run_diff(self, a, b, from_file, to_file, **options):
        external_diff_tool = options.get('cmd')

        (from_content, from_file) = self.prep_content(a, from_file, 'from_file')
        (to_content, to_file) = self.prep_content(b, to_file, 'to_file')

        diffs = list(difflib.unified_diff(from_content, to_content, from_file, to_file))

        if not diffs:
            sublime.status_message('No Difference')
        else:
            external_command = external_diff_tool or self.settings().get('cmd')
            open_in_sublime = self.settings().get('open_in_sublime', not external_command)

            if external_command:
                self.diff_with_external(external_command, a, b, from_file, to_file)

            if open_in_sublime:
                # fix diffs
                diffs = map(lambda line: (line and line[-1] == "\n") and line or line + "\n", diffs)
                self.diff_in_sublime(diffs)

    def diff_with_external(self, external_command, a, b, from_file=None, to_file=None):
        try:
            try:
                from_file_exists = os.path.exists(from_file)
            except ValueError:
                from_file_exists = False

            try:
                to_file_exists = os.path.exists(to_file)
            except ValueError:
                to_file_exists = False

            if not from_file_exists:
                tmp_file = tempfile.NamedTemporaryFile(delete=False)
                from_file = tmp_file.name
                tmp_file.close()

                with codecs.open(from_file, encoding='utf-8', mode='w+') as tmp_file:
                    tmp_file.write(a)

            if not to_file_exists:
                tmp_file = tempfile.NamedTemporaryFile(delete=False)
                to_file = tmp_file.name
                tmp_file.close()

                with codecs.open(to_file, encoding='utf-8', mode='w+') as tmp_file:
                    tmp_file.write(b)

            trim_trailing_white_space_before_diff = self.settings().get('trim_trailing_white_space_before_diff', False)
            if trim_trailing_white_space_before_diff:
                def trim_trailing_white_space(file_name):
                    trim_lines = []
                    modified = False
                    with codecs.open(file_name, encoding='utf-8', mode='r') as f:
                        lines = f.readlines()
                        lines = [line.replace("\n", "").replace("\r", "") for line in lines]
                        for line in lines:
                            trim_line = line.rstrip()
                            trim_lines.append(trim_line)
                            if trim_line != line:
                                modified = True
                    if modified:
                        tmp_file = tempfile.NamedTemporaryFile(delete=False)
                        file_name = tmp_file.name
                        tmp_file.close()
                        with codecs.open(file_name, encoding='utf-8', mode='w+') as f:
                            f.writelines('\n'.join(trim_lines))
                    return file_name

                from_file = trim_trailing_white_space(from_file)
                to_file = trim_trailing_white_space(to_file)

            if os.path.exists(from_file):
                external_command = [c.replace('$file1', from_file) for c in external_command]
                external_command = [c.replace('$file2', to_file) for c in external_command]
                if sublime.platform() == "windows":
                    Popen(external_command)
                else:
                    self.view.window().run_command("exec", {"cmd": external_command})
        except Exception as e:
            # some basic logging here, since we are cluttering the /tmp folder
            sublime.status_message(str(e))

    def diff_in_sublime(self, diffs):
        diffs = ''.join(diffs)
        scratch = self.view.window().new_file()
        scratch.set_scratch(True)
        scratch.set_syntax_file('Packages/Diff/Diff.tmLanguage')
        scratch.run_command('file_diff_dummy1', {'content': diffs})

    def read_file(self, file_name):
        content=""
        with codecs.open(file_name, mode='U', encoding='utf-8') as f:
            content = f.read()
        return content


class FileDiffDummy1Command(sublime_plugin.TextCommand):
    def run(self, edit, content):
        self.view.insert(edit, 0, content)


class FileDiffClipboardCommand(FileDiffCommand):
    def run(self, edit, **kwargs):
        from_file = self.view.file_name()
        for region in self.view.sel():
            if not region.empty():
                from_file += ' (Selection)'
                break
        clipboard = sublime.get_clipboard()
        self.run_diff(self.diff_content(), clipboard,
            from_file=from_file,
            to_file='(clipboard)',
            **kwargs)


class FileDiffSelectionsCommand(FileDiffCommand):
    def trim_indent(self, lines):
        indent = None
        for line in lines:
            # ignore blank lines
            if line == '':
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


class FileDiffSavedCommand(FileDiffCommand):
    def run(self, edit, **kwargs):
        self.run_diff(self.read_file(self.view.file_name()), self.diff_content(),
            from_file=self.view.file_name(),
            to_file=self.view.file_name() + ' (Unsaved)',
            **kwargs)


class FileDiffFileCommand(FileDiffCommand):
    def run(self, edit, **kwargs):
        common = None
        folders = self.view.window().folders()
        files = self.find_files(folders)
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
        files = [file for file in files if file != my_file]
        # shorten names using common length
        file_picker = [file[len(common):] for file in files]

        def on_done(index):
            if index > -1:
                self.run_diff(self.diff_content(), self.read_file(files[index]),
                    from_file=self.view.file_name(),
                    to_file=files[index],
                    **kwargs)
        sublime.set_timeout(lambda: self.view.window().show_quick_panel(file_picker, on_done), 1)

    def find_files(self, folders, ret=[]):
        # Cannot access these settings!!  WHY!?
        # folder_exclude_patterns = self.view.settings().get('folder_exclude_patterns')
        # file_exclude_patterns = self.view.settings().get('file_exclude_patterns')
        folder_exclude_patterns = [".svn", ".git", ".hg", "CVS"]
        file_exclude_patterns = ["*.pyc", "*.pyo", "*.exe", "*.dll", "*.obj", "*.o", "*.a", "*.lib", "*.so", "*.dylib", "*.ncb", "*.sdf", "*.suo", "*.pdb", "*.idb", ".DS_Store", "*.class", "*.psd", "*.db"]
        max_files = self.settings().get('limit', 1000)

        for folder in folders:
            if not os.path.isdir(folder):
                continue

            for file in os.listdir(folder):
                fullpath = os.path.join(folder, file)
                if os.path.isdir(fullpath):
                    # excluded folder?
                    if not len([True for pattern in folder_exclude_patterns if fnmatch(file, pattern)]):
                        self.find_files([fullpath], ret)
                else:
                    # excluded file?
                    if not len([True for pattern in file_exclude_patterns if fnmatch(file, pattern)]):
                        ret.append(fullpath)
                if len(ret) >= max_files:
                    sublime.status_message('Too many files to include all of them in this list')
                    return ret
        return ret


class FileDiffTabCommand(FileDiffCommand):
    def run(self, edit, **kwargs):
        my_id = self.view.id()
        files = []
        contents = []
        untitled_count = 1
        for v in self.view.window().views():
            if v.id() != my_id:
                this_content = v.substr(sublime.Region(0, v.size()))
                if v.file_name():
                    files.append(v.file_name())
                elif v.name():
                    files.append(v.name())
                else:
                    files.append('untitled %d' % untitled_count)
                    untitled_count += 1

                contents.append(this_content)

        def on_done(index):
            if index > -1:
                self.run_diff(self.diff_content(), contents[index],
                    from_file=self.view.file_name(),
                    to_file=files[index],
                    **kwargs)

        if len(files) == 1:
            on_done(0)
        else:
            menu_items = [os.path.basename(f) for f in files]
            sublime.set_timeout(lambda: self.view.window().show_quick_panel(menu_items, on_done), 1)


previous_view = current_view = None

class FileDiffPreviousCommand(FileDiffCommand):
    def run(self, edit, **kwargs):
        if previous_view:
            previous_view_content = previous_view.substr(sublime.Region(0, previous_view.size()))
            previous_view_name = ''
            if previous_view.file_name():
                previous_view_name = previous_view.file_name()
            elif previous_view.name():
                previous_view_name = previous_view.name()
            else:
                previous_view_name = 'untitled (Previous)'

            view_name = ''
            if self.view.file_name():
                view_name = self.view.file_name()
            elif self.view.name():
                view_name = self.view.name()
            else:
                view_name = 'untitled (Current)'

            self.run_diff(previous_view_content, self.diff_content(),
                from_file=previous_view_name,
                to_file=view_name,
                **kwargs)

def record_current_view(view):
    global previous_view
    global current_view
    previous_view = current_view
    current_view = view

class FileDiffListener(sublime_plugin.EventListener):
    def on_activated(self, view):
        try:
            # Prevent 'show_quick_panel()' of 'FileDiffs Menu' from being recorded
            view.window().views()
            if current_view is None or view.id() != current_view.id():
                record_current_view(view)
        except AttributeError:
            pass
