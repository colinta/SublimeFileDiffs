# coding: utf8

import sublime
import sublime_plugin
import subprocess

import os
from fnmatch import fnmatch
from tempfile import mkstemp


CLIPBOARD = u'Diff file with Clipboard'
SELECTIONS = u'Diff Selections'
SAVED = u'Diff file with Saved'
FILE = u'Diff file with File in Project…'
TAB = u'Diff file with Open Tab…'


FILE_DIFFS = [CLIPBOARD, SAVED, FILE, TAB]


class FileDiffMenuCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        menu_items = FILE_DIFFS
        regions = self.view.sel()
        if len(regions) == 1 and not regions[0].empty():
            menu_items = [f.replace(u'Diff file', u'Diff selection') for f in FILE_DIFFS]
        elif len(regions) == 2:
            menu_items.insert(1, SELECTIONS)

        def on_done(index):
            if index == -1:
                return
            elif FILE_DIFFS[index] == CLIPBOARD:
                self.view.run_command('file_diff_clipboard')
            elif FILE_DIFFS[index] == SELECTIONS:
                self.view.run_command('file_diff_selections')
            elif FILE_DIFFS[index] == SAVED:
                self.view.run_command('file_diff_saved')
            elif FILE_DIFFS[index] == FILE:
                self.view.run_command('file_diff_file')
            elif FILE_DIFFS[index] == TAB:
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
            content = self.view.file_name()
        return content

    def run_diff(self, a, b):
        a = a.encode('utf-8')
        b = b.encode('utf-8')

        delete = []
        if not os.path.exists(a):
            prefix, suffix = os.path.splitext(self.view.file_name())
            prefix += '_'
            fd, path = mkstemp(suffix, prefix)
            os.write(fd, a)
            os.close(fd)
            delete.append(path)
            a = path

        if not os.path.exists(b):
            prefix, suffix = os.path.splitext(self.view.file_name())
            prefix += '_'
            fd, path = mkstemp(suffix, prefix)
            os.write(fd, b)
            os.close(fd)
            delete.append(path)
            b = path

        p = subprocess.Popen(['diff', '-wru', a, b], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        diff = p.stdout.read()
        diff = unicode(diff, 'utf-8')

        for path in delete:
            os.remove(path)

        return diff

    def show_diff(self, diff):
        if diff == '':
            sublime.status_message('No Difference')
        else:
            panel = self.view.window().new_file()
            panel.set_scratch(True)
            panel.set_syntax_file('Packages/Diff/Diff.tmLanguage')
            panel_edit = panel.begin_edit('file_diffs')
            panel.insert(panel_edit, 0, diff)
            panel.end_edit(panel_edit)


class FileDiffClipboardCommand(FileDiffCommand):
    def run(self, edit, **kwargs):
        current = sublime.get_clipboard()
        diff = self.run_diff(self.diff_content(), current)
        self.show_diff(diff)


class FileDiffSelectionsCommand(FileDiffCommand):
    def run(self, edit, **kwargs):
        regions = self.view.sel()
        current = self.view.substr(regions[0])
        diff = self.view.substr(regions[1])
        diff = self.run_diff(current, diff)
        self.show_diff(diff)


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

        diff = self.run_diff(self.view.file_name(), content)
        self.show_diff(diff)


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
                diff = self.run_diff(self.diff_content(), files[index])
                self.show_diff(diff)
        self.view.window().show_quick_panel(file_picker, on_done)

    def find_files(self, folders):
        # Cannot access these settings!!  WHY!?
        # folder_exclude_patterns = self.view.settings().get('folder_exclude_patterns')
        # file_exclude_patterns = self.view.settings().get('file_exclude_patterns')
        folder_exclude_patterns = [".svn", ".git", ".hg", "CVS"]
        file_exclude_patterns = ["*.pyc", "*.pyo", "*.exe", "*.dll", "*.obj", "*.o", "*.a", "*.lib", "*.so", "*.dylib", "*.ncb", "*.sdf", "*.suo", "*.pdb", "*.idb", ".DS_Store", "*.class", "*.psd", "*.db"]

        ret = []
        for folder in folders:
            for file in os.listdir(folder):
                fullpath = folder + '/' + file
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
        my_file = self.view.file_name()
        files = [v.file_name() for v in self.view.window().views() if v.file_name() != my_file]

        def on_done(index):
            if index > -1:
                diff = self.run_diff(self.diff_content(), files[index])
                self.show_diff(diff)
        if len(files) == 1:
            on_done(0)
        else:
            menu_items = [os.path.basename(f) for f in files]
            self.view.window().show_quick_panel(menu_items, on_done)
