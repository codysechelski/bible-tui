# ==== Output =================================================================
Output videos/version-switching.mp4


# ==== Settings ===============================================================
Source ../settings.tape


# ==== Setup ==================================================================
Source ../setup.tape


# ==== Steps ==================================================================
# ---- Open the app -----------------------------------------------------------
Sleep 500ms
Type@220ms "bible-tui asv"
Sleep 500ms
Enter
Sleep 1s

# ---- Pick a version with t --------------------------------------------------
Type ":"
Sleep 800ms
Type@400ms "john"
Tab
Type "3"
Sleep 500ms
Tab
Type "16"
Sleep 800ms
Enter
Sleep 2s
Type "t"
Screenshot screenshots/showing-version-picker-modal.png
Sleep 3s
Type@200ms "jj"
Enter
Sleep 2s

# ---- Pick a version from the : command line ---------------------------------
Type@330ms ":set"
Tab
Screenshot screenshots/showing-version-picker-command-line.png
Sleep 3s
Type@200ms "b"
Sleep 330ms
Tab
Sleep 300ms
Enter
# Now on the Bíblia Livre to the end.
#@ footnote bible-livre
Sleep 5s


# ==== Teardown ===============================================================
Source ../teardown.tape
