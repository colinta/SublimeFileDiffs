# coding: utf8
import os
import re

import sublime
import sublime_plugin
import difflib
import tempfile

from fnmatch import fnmatch
import codecs

SETTINGS = sublime.load_settings('FileDiffs.sublime-settings')

CLIPBOARD = u'Diff file with Clipboard'
SELECTIONS = u'Diff Selections'
SAVED = u'Diff file with Saved'
FILE = u'Diff file with File in Project…'
TAB = u'Diff file with Open Tab…'

FILE_DIFFS = [CLIPBOARD, SAVED, FILE, TAB]


class FileDiffMenuCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        menu_items = FILE_DIFFS[:]
        saved = SAVED
        non_empty_regions = [region for region in self.view.sel() if not region.empty()]
        if len(non_empty_regions) == 2:
            menu_items.insert(1, SELECTIONS)
        elif len(non_empty_regions):
            menu_items = [f.replace(u'Diff file', u'Diff selection') for f in menu_items]
            saved = saved.replace(u'Diff file', u'Diff selection')

        if not (self.view.file_name() and self.view.is_dirty()):
            menu_items.remove(saved)

        def on_done(index):
            restored_menu_items = [f.replace(u'Diff selection', u'Diff file') for f in menu_items]
            if index == -1:
                return
            elif restored_menu_items[index] == CLIPBOARD:
                self.view.run_command('file_diff_clipboard')
            elif restored_menu_items[index] == SELECTIONS:
                self.view.run_command('file_diff_selections')
            elif restored_menu_items[index] == SAVED:
                self.view.run_command('file_diff_saved')
            elif restored_menu_items[index] == FILE:
                self.view.run_command('file_diff_file')
            elif restored_menu_items[index] == TAB:
                self.view.run_command('file_diff_tab')
        self.view.window().show_quick_panel(menu_items, on_done)


class FileDiffCommand(sublime_plugin.TextCommand):
    def diff_content(self):
        content = ''

        regions = [region for region in self.view.sel()]
        for region in regions:
            if region.empty():
                continue
            content += self.view.substr(region)

        if not content:
            content = self.view.substr(sublime.Region(0, self.view.size()))
        return content

    def run_diff(self, a, b, from_file=None, to_file=None):
        from_content = a
        to_content = b

        if os.path.exists(a):
            if from_file is None:
                from_file = a
            with codecs.open(from_file, mode='U', encoding='utf-8') as f:
                from_content = f.readlines()
        else:
            from_content = a.splitlines(True)
            if from_file is None:
                from_file = 'from_file'

        if os.path.exists(b):
            if to_file is None:
                to_file = b
            with codecs.open(to_file, mode='U', encoding='utf-8') as f:
                to_content = f.readlines()
        else:
            to_content = b.splitlines(True)
            if to_file is None:
                to_file = 'to_file'

        diffs = list(difflib.unified_diff(from_content, to_content, from_file, to_file))

        open_in_sublime = SETTINGS.get('open_in_sublime', True)
        external_command = SETTINGS.get('cmd')
        if not diffs:
            sublime.status_message('No Difference')
        else:
            if external_command:
                self.diff_with_external(a, b, from_file, to_file)

            if open_in_sublime:
                self.diff_in_sublime(diffs)

    def diff_with_external(self, a, b, from_file=None, to_file=None):
        try:
            if not os.path.exists(from_file):
                tmp_file = tempfile.NamedTemporaryFile(delete=False)
                from_file = tmp_file.name
                tmp_file.close()

                with codecs.open(from_file, encoding='utf-8', mode='w+') as tmp_file:
                    tmp_file.write(a)

            if not os.path.exists(to_file):
                tmp_file = tempfile.NamedTemporaryFile(delete=False)
                to_file = tmp_file.name
                tmp_file.close()

                with codecs.open(to_file, encoding='utf-8', mode='w+') as tmp_file:
                    tmp_file.write(b)

            if os.path.exists(from_file):
                command = SETTINGS.get('cmd')
                if command is not None:
                    command = [c.replace(u'$file1', from_file) for c in command]
                    command = [c.replace(u'$file2', to_file) for c in command]
                    self.view.window().run_command("exec", {"cmd": command})
        except Exception as e:
            # some basic logging here, since we are cluttering the /tmp folder
            print repr(e)
            sublime.status_message(str(e))

    def diff_in_sublime(self, diffs):
        scratch = self.view.window().new_file()
        scratch.set_scratch(True)
        scratch.set_syntax_file('Packages/Diff/Diff.tmLanguage')
        scratch_edit = scratch.begin_edit('file_diffs')
        scratch.insert(scratch_edit, 0, ''.join(diffs))
        scratch.end_edit(scratch_edit)


class FileDiffClipboardCommand(FileDiffCommand):
    def run(self, edit, **kwargs):
        current = sublime.get_clipboard()
        self.run_diff(self.diff_content(), current,
            from_file=self.view.file_name(),
            to_file='(clipboard)')


class FileDiffSelectionsCommand(FileDiffCommand):
    def run(self, edit, **kwargs):
        regions = self.view.sel()
        current = self.view.substr(regions[0])
        diff = self.view.substr(regions[1])

        # trim off indent
        indent = None
        for line in current.splitlines():
            new_indent = re.match('[ \t]*', line).group(0)
            if new_indent == '':
                continue

            if indent is None:
                indent = new_indent
            elif len(new_indent) < len(indent):
                indent = new_indent

            if not indent:
                break

        if indent:
            current = u"\n".join(line[len(indent):] for line in current.splitlines())

        # trim off indent
        indent = None
        for line in diff.splitlines():
            new_indent = re.match('[ \t]*', line).group(0)
            if new_indent == '':
                continue

            if indent is None:
                indent = new_indent
            elif len(new_indent) < len(indent):
                indent = new_indent

        if indent:
            diff = u"\n".join(line[len(indent):] for line in diff.splitlines())

        self.run_diff(current, diff,
            from_file='first selection',
            to_file='second selection')


class FileDiffSavedCommand(FileDiffCommand):
    def run(self, edit, **kwargs):
        content = ''
        regions = [region for region in self.view.sel()]
        for region in regions:
            if region.empty():
                continue
            content += self.view.substr(region)
        if not content:
            content = self.view.substr(sublime.Region(0, self.view.size()))

        self.run_diff(self.view.file_name(), content,
            from_file=self.view.file_name(),
            to_file=self.view.file_name() + u' (Unsaved)')


class FileDiffFileCommand(FileDiffCommand):
    def run(self, edit, **kwargs):
        common = None
        folders = self.view.window().folders()
        files = self.find_files(folders)
        for folder in folders:
            if common == None:
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
                self.run_diff(self.diff_content(), files[index],
                    from_file=self.view.file_name())
        self.view.window().show_quick_panel(file_picker, on_done)

    def find_files(self, folders):
        # Cannot access these settings!!  WHY!?
        # folder_exclude_patterns = self.view.settings().get('folder_exclude_patterns')
        # file_exclude_patterns = self.view.settings().get('file_exclude_patterns')
        folder_exclude_patterns = [".svn", ".git", ".hg", "CVS"]
        file_exclude_patterns = ["*.pyc", "*.pyo", "*.exe", "*.dll", "*.obj", "*.o", "*.a", "*.lib", "*.so", "*.dylib", "*.ncb", "*.sdf", "*.suo", "*.pdb", "*.idb", ".DS_Store", "*.class", "*.psd", "*.db"]

        ret = []
        for folder in folders:
            if not os.path.isdir(folder):
                continue

            for file in os.listdir(folder):
                fullpath = os.path.join(folder, file)
                if os.path.isdir(fullpath):
                    # excluded folder?
                    if not len([True for pattern in folder_exclude_patterns if fnmatch(file, pattern)]):
                        ret += self.find_files([fullpath])
                else:
                    # excluded file?
                    if not len([True for pattern in file_exclude_patterns if fnmatch(file, pattern)]):
                        ret.append(fullpath)
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
                    to_file=files[index])

        if len(files) == 1:
            on_done(0)
        else:
            menu_items = [os.path.basename(f) for f in files]
            self.view.window().show_quick_panel(menu_items, on_done)
