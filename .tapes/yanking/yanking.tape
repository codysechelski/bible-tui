# ==== Output =================================================================
Output videos/yanking.mp4


# ==== Settings ===============================================================
Source ../settings.tape


# ==== Setup ==================================================================
Source ../setup.tape

# setup.sh builds a throwaway HOME (the clean app home from setup.tape, a plain prompt, nvim set to wrap
# and paste from the clipboard) and attaches to a private tmux server: a shell left, nvim notes.md right.
Hide
Type "./setup.sh"
Enter
Sleep 3s
Show


# ==== Steps ==================================================================
# ---- Open the app -----------------------------------------------------------
Sleep 1s
Type@120ms "bible-tui"
Sleep 400ms
Enter
Sleep 1.5s

# ---- 1. Go to a verse with ctrl+g, copy part of it in visual mode -----------
Ctrl+G
Sleep 600ms
Type@250ms "ps"
Sleep 300ms
Tab
Type@250ms "119"
Sleep 300ms
Tab
Type@250ms "105"
Sleep 600ms
Enter
Sleep 1s
# "Thy word is " is 12 characters; select "a lamp unto my feet", overshooting by two and backing up.
Type@90ms "llllllllllll"
Sleep 400ms
Type "v"
Sleep 400ms
Type@90ms "llllllllllllllllllll"
Sleep 400ms
Type@300ms "hh"
Sleep 600ms
Type "y"
Sleep 1s

# Paste into the notes pane and leave some space below it.
Ctrl+B
Right
Sleep 600ms
# A heading saying what this example shows, a blank line, then the paste.
Type "i"
Type@50ms "## Part of a verse"
Enter@250ms 2
Escape
Sleep 400ms
Type "p"
Sleep 800ms
Type@200ms "Go"
Enter@250ms 2
Escape
Sleep 800ms
Ctrl+B
Left
Sleep 800ms

# ---- 2. Find a book with / and copy several verses in visual line mode ------
Type "0"
Sleep 300ms
Type@400ms "hh"
Sleep 600ms
Type "/"
Sleep 300ms
Type@250ms "ephe"
Sleep 500ms
Enter
Sleep 300ms
Escape
Sleep 500ms
Type "l"
Sleep 400ms
Type "j"
Sleep 400ms
Type "l"
Sleep 500ms
Type@200ms "jjjjjjj"
Sleep 600ms
Type "V"
Sleep 400ms
Type@400ms "jj"
Sleep 600ms
Type "y"
Sleep 1s

Ctrl+B
Right
Sleep 600ms
# A heading saying what this example shows, a blank line, then the paste.
Type "i"
Type@50ms "## Multiple verses"
Enter@250ms 2
Escape
Sleep 400ms
Type "p"
Sleep 800ms
Type@200ms "Go"
Enter@250ms 2
Escape
Sleep 800ms
Ctrl+B
Left
Sleep 800ms

# ---- 3. Go to a verse from the : command line and copy it with yy -----------
Type ":"
Sleep 500ms
Type@250ms "joh"
Sleep 300ms
Tab
Type@250ms "3"
Sleep 300ms
Tab
Type@250ms "16"
Sleep 600ms
Enter
Sleep 1s
Type@250ms "yy"
Sleep 1s

Ctrl+B
Right
Sleep 600ms
# A heading saying what this example shows, a blank line, then the paste.
Type "i"
Type@50ms "## One verse"
Enter@250ms 2
Escape
Sleep 400ms
Type "p"
Sleep 800ms
Type@200ms "Go"
Enter@250ms 2
Escape
Sleep 800ms
Ctrl+B
Left
Sleep 800ms

# ---- 4. Add a yank_format to config.json and copy the same verse again ------
Type@250ms ":q"
Sleep 400ms
Enter
Sleep 800ms
Type@60ms "nvim ~/.config/bible-tui/config.json"
Sleep 400ms
Enter
Sleep 1.5s
# The last setting is the line above the closing brace: add a comma, then the new setting.
Type "G"
Sleep 300ms
Type "k"
Sleep 300ms
Type "A"
Sleep 300ms
Type ","
Enter
Type@100ms `"yank_format": "{text}\n\n  ~ {reference} {version}"`
Sleep 1s
Escape
Sleep 600ms
Type@200ms ":wq"
Sleep 600ms
Enter
Sleep 800ms
Type@120ms "bible-tui"
Sleep 300ms
Enter
Sleep 1.5s

Type ":"
Sleep 500ms
Type@250ms "joh"
Sleep 300ms
Tab
Type@250ms "3"
Sleep 300ms
Tab
Type@250ms "16"
Sleep 600ms
Enter
Sleep 1s
Type@250ms "yy"
Sleep 1s

Ctrl+B
Right
Sleep 600ms
# A heading saying what this example shows, a blank line, then the paste.
Type "i"
Type@50ms "## yy with a yank_format"
Enter@250ms 2
Escape
Sleep 400ms
Type "p"
Sleep 800ms
# Jump to the end so the "~ John 3:16 ASV" line is on screen for the final hold.
Type "G"
Sleep 5s


# ==== Teardown ===============================================================
# Stop the private tmux server, or it keeps running after VHS finishes.
Hide
Ctrl+B
Type ":kill-server"
Enter
Sleep 500ms

# Then the shared teardown, back in the outer shell where the real HOME is set.
Source ../teardown.tape
