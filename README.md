FileDiffs Plugin for Sublime Text 2
===================================

Shows diffs - also in an external diff tool - between the current file, or selection(s) in the current file, and clipboard, another file, or unsaved changes.


Installation
------------

1. Using Package Control, install "FileDiffs"

Or:

1. Open the Sublime Text 2 Packages folder

    - OS X: ~/Library/Application Support/Sublime Text 2/Packages/
    - Windows: %APPDATA%/Sublime Text 2/Packages/
    - Linux: ~/.Sublime Text 2/Packages/

2. clone this repo
3. Install keymaps for the commands (see Example.sublime-keymap for my preferred keys)

Add External Diff Tool
--------

(IMPORTANT: Dont forget to make a correct symlink (e.g. in /usr/bin) pointing to the command line tool of your external diff tool)

1. Preferences > Package Settings > FileDiffs > Settings - Default

2. Uncomment one of the examples or write you own command to open external diff tool.


Commands
--------

`file_diff_menu`: Shows a menu to select one of the file_diff commands.  Bound to `ctrl+shift+d`.

The rest of the commands are not bound by default:

`file_diff_clipboard`: Shows the diff of the current file or selection(s) and the clipboard (the clipboard is considered the "new" file unless `reverse` is True)

`file_diff_selections`: Shows the diff of the first and second selected regions.  The file_diff_menu command checks for exactly two regions selected, otherwise it doesn't display this command.

`file_diff_saved`: Shows the diff of the current file or selection(s) and the saved file.

`file_diff_file`: Shows the diff of the current file or selection(s) and a file that is in the current project.

`file_diff_tab`: Shows the diff of the current file or selection(s) and an open file (aka a file that has a tab).
