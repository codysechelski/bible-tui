# ==== Output =================================================================
Output videos/marks.mp4


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

# ---- Mark a verse -----------------------------------------------------------
Type ":"
Sleep 800ms
Type@400ms "john"
Tab@800ms
Type "3"
Sleep 500ms
Tab@500ms
Type "16"
Sleep 800ms
Enter@500ms
Sleep 2s
Type "m"
Screenshot screenshots/showing-marked-verse.png
Enter
Sleep 1s

# ---- Mark a verse, unmark it, mark it again ---------------------------------
Ctrl+G
Type@330ms "pr"
Sleep 350ms
Tab
Type@200ms "16"
Sleep 175ms
Tab
Type@220ms "3"
Sleep 120ms
Enter
Sleep 1s
Type "m"
Sleep 500ms
Type "m"
Sleep 500ms
Type "m"
Sleep 1s

# ---- Mark several verses ----------------------------------------------------
Type@300ms "hh"
Sleep 600ms
Type@450ms "/1 co"
Enter
Sleep 500ms
Type "n"
Sleep 400ms
Enter
Escape
Sleep 300ms
Type@200ms "l"
Type@120ms "jjjjjjjjjjjj"
Type@200ms "l"
Type@100ms "jjj"
Type@505ms "Vjjj"
Sleep 400ms
Type@400ms "m"
Enter
Sleep 1s

# ---- Show the marks list and jump to one ------------------------------------
Type "M"
Sleep 1s
Screenshot screenshots/showing-marks-list.png
Type@330ms "jjjj"
Enter
Sleep 500ms
Type "M"
Sleep 400ms
Type@300ms "jj"
Enter
Sleep 5s


# ==== Teardown ===============================================================
Source ../teardown.tape
