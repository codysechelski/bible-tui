# ==== Output =================================================================
Output videos/your-files.mp4


# ==== Settings ===============================================================
Source ../settings.tape


# ==== Setup ==================================================================
Source ../setup.tape

# A throwaway HOME with config.json kept in ~/dotfiles and linked into the app home (see setup.sh).
Hide
Type "../sandbox your-files ./setup.sh"
Enter
Sleep 1s
Type "clear"
Enter
Sleep 500ms
Show


# ==== Steps ==================================================================
# ---- Mark a verse and highlight another, then quit -------------------------
Sleep 500ms
Type@120ms "bible-tui"
Sleep 400ms
Enter
Sleep 1.5s
Type ":"
Sleep 400ms
Type@200ms "john 3:16"
Sleep 400ms
Enter
Sleep 800ms
Type "m"
Sleep 800ms
Ctrl+G
Sleep 400ms
Type@200ms "ps"
Tab
Type@200ms "23"
Tab
Type@200ms "1"
Sleep 400ms
Enter
Sleep 800ms
Type "c"
Sleep 600ms
Type "2"
Sleep 1s
Type "q"
Sleep 800ms

# ---- Everything is a plain JSON file in one folder ------------------------
Type@60ms "cd ~/.config/bible-tui"
Enter
Sleep 400ms
Type@60ms "clear; tree -aC"
Enter
Sleep 2s
Screenshot screenshots/showing-saved-file-structure.png
Sleep 1s
Type@60ms "bat --style=plain --paging=never marks.json highlights.json"
Enter
Sleep 4s

# ---- config.json lives in a dotfiles repo ---------------------------------
Type@60ms "clear; ls -l config.json"
Enter
Sleep 2s
Type@60ms "cd ~/dotfiles && git log --oneline"
Enter
Sleep 1.5s
Type@60ms "bat --style=plain --paging=never bible-tui/.config/bible-tui/config.json"
Enter
Sleep 2s
Screenshot screenshots/stowable-config-file.png
Sleep 4s


# ==== Teardown ===============================================================
# Leave the sandbox shell, then the shared teardown in the tape's own shell.
Hide
Type "exit"
Enter
Sleep 500ms
Source ../teardown.tape
