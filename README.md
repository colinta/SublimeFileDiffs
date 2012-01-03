FileDiffs Plugin for Sublime Text 2
===================================

Show diffs between the current file, or selection(s) in the current file, and clipboard, another file, or unsaved changes.


Installation
------------

1. Open the Sublime Text 2 Packages folder

    - OS X: ~/Library/Application Support/Sublime Text 2/Packages/
    - Windows: %APPDATA%/Sublime Text 2/Packages/
    - Linux: ~/.Sublime Text 2/Packages/

2. clone this repo

Commands
--------

`file_diff_menu`: Shows a menu to select one of the file_diff commands.  Bound to `ctrl+shift+d`.

The rest of the commands are not bound by default:

`file_diff_clipboard`: Shows the diff of the current file or selection(s) and the clipboard (the clipboard is considered the "new" file unless `reverse` is True)

`file_diff_saved`: Shows the diff of the current file or selection(s) and the saved file.

`file_diff_file`: Shows the diff of the current file or selection(s) and a file that is in the current project.

`file_diff_tab`: Shows the diff of the current file or selection(s) and an open file (aka a file that has a tab).
