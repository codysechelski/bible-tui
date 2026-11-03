# ==== Output =================================================================
Output videos/fuzzy-finding.mp4


# ==== Settings ===============================================================
Source ../settings.tape


# ==== Setup ==================================================================
Source ../setup.tape


# ==== Steps ==================================================================
# ---- Open the app -----------------------------------------------------------
Sleep 500ms
Type@220ms "bible-tui"
Sleep 500ms
Enter
Sleep 1s

# ---- Truly Fuzzy Searches --------------------------------------------------
Ctrl+S
Sleep 1s
Type@400ms "wages sin death"
Screenshot screenshots/showing-fuzzy-find-multi-word.png
Sleep 500ms
Enter

Sleep 2s
Type ":"
Sleep 300ms
Type@220ms "find"
Sleep 300ms
Enter
Sleep 500ms
Type@330ms "godlovwor"
Screenshot screenshots/showing-fuzzy-find-no-spaces.png
Sleep 2s
Down@200ms 2
Up@330ms 2
Sleep 330ms
Enter
Sleep 2s

# ---- Fuzzy Searches using '  ------------------------------------------------
Ctrl+S
Sleep 1s
Type@300ms "zac"
Sleep 3s
Backspace@600ms 3
Type@400ms "'zac"
Sleep 3s
Down@200ms 3
Enter
Sleep 2s

Ctrl+S
Sleep 500ms
Type@160ms "faith works"
Sleep 3s
Backspace@400ms 11
Type@420ms "'faith' 'works'"
Screenshot screenshots/showing-fuzzy-find-whole-words.png
Sleep 3s
Enter
Sleep 2s

# ---- Fuzzy Searches using ^  ------------------------------------------------
Type ":"
Sleep 600ms
Type@220ms "find"
Sleep 300ms
Enter
Sleep 1s
Type@145ms "watch"
Sleep 3s
Backspace@200ms 5
Type@200ms "^watch"
Screenshot screenshots/showing-fuzzy-find-starts-with.png
Sleep 3s
Enter
Sleep 2s

# ---- Fuzzy Searches using $  ------------------------------------------------
Type ":"
Sleep 600ms
Type@220ms "find"
Sleep 500ms
Type@300ms " king."
Enter
Sleep 3s
Backspace@200ms 5
Type@200ms "king.$"
Screenshot screenshots/showing-fuzzy-find-ends-with.png
Sleep 3s
Enter

Sleep 5s


# ==== Teardown ===============================================================
Source ../teardown.tape
