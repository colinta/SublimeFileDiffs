# `FileDiffs` plugin for [Sublime Text 2](http://www.sublimetext.com/2)

Shows diffs inside ST2 or via an external diff tool, between: The current file, or selection(s) in the current file, and clipboard, another file, or unsaved changes.

## Installation

1. Using [Package Control](http://wbond.net/sublime_packages/package_control), `install "FileDiffs"`.

**… or:**

1. Open the ST2 `Packages` folder:
    * **OS X:** `~/Library/Application Support/Sublime Text 2/Packages/`
    * **Windows:** `%APPDATA%/Sublime Text 2/Packages/`
    * **Linux:** `~/.Sublime Text 2/Packages/`

1. Clone this repo.
1. Install keymaps for the commands (see [`Example.sublime-keymap`](https://github.com/colinta/SublimeFileDiffs/blob/master/Example.sublime-keymap) for [@colinta](https://github.com/colinta)'s preferred key mappings).

## Add external diff tool

1. Open `Preferences` > `Package Settings` > `FileDiffs` > `Settings - Default`.

1. Uncomment one of the examples or write you own command to open an external diff tool of your choice.

**IMPORTANT:** *Dont forget* to make a correct symlink (e.g. in `/usr/bin`) pointing to the command line tool of your external diff tool. **For example**, if you're running [Mac OS X Mountain Lion](http://www.apple.com/osx/) and you want to use [Kaleidoscope](http://www.kaleidoscopeapp.com/):

1. Add your key bindings:
    * Open `Sublime Text 2` > `Preferences` > `Key Bindings - User` and add `{ "keys": ["ctrl+shift+d"], "command": "file_diff_menu" }`.
    * [Here's an example](https://github.com/colinta/SublimeFileDiffs/blob/master/Example.sublime-keymap).
1. Add a command:
    * Open `Sublime Text 2` > `Preferences` > `Package Settings` > `FileDiffs` > `Settings - User` and add `"cmd": ["ksdiff", "$file1", "$file2"]`.
    * [Here's an example](https://github.com/colinta/SublimeFileDiffs/blob/master/FileDiffs.sublime-settings) (just uncomment the the `ksdiff` line).
1. Create a symlink:
    * Open `terminal` and run `sudo ln -s /Applications/Kaleidoscope.app/Contents/MacOS/ksdiff /usr/bin`; this will create a symbolic link to the `ksdiff` command line tool.
1. Compare files:
    * Open two files that you want to compare and run your key binding (`ctrl` + `shift` + `d`).
    * From the menu that opens (`file_diff_menu`, see below), choose `Diff file with Open Tab…`. If everything is setup correctly, then `Kaleidoscope.app` will open and you can start comparing the diffs.

## Commands

* `file_diff_menu`: Shows a menu to select one of the `file_diff` commands. Bound to `ctrl` + `shift` + `d`, for example, via your keymap settings.

~~The rest of the commands are not bound by default:~~

Other available commands:

* `file_diff_clipboard`: Shows the diff of the current file or selection(s) and the clipboard (the clipboard is considered the "new" file unless `reverse` is `True`).
* `file_diff_selections`: Shows the diff of the first and second selected regions. The `file_diff_menu` command checks for exactly two regions selected, otherwise it doesn't display this command.
* `file_diff_saved`: Shows the diff of the current file or selection(s) and the saved file.
* `file_diff_file`: Shows the diff of the current file or selection(s) and a file that is in the current project.
* `file_diff_tab`: Shows the diff of the current file or selection(s) and an open file (e.g. a file that's open in a tab).