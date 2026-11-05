# ==== Output =================================================================
Output videos/commands.mp4


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

# ---- Open the commands modal with ? and scroll through it -------------------
Type "?"
Screenshot screenshots/commands.png
Sleep 1s
Down@450ms 46
Sleep 3s
Escape
Sleep 5s


# ==== Teardown ===============================================================
Source ../teardown.tape
