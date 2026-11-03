# ==== Output =================================================================
Output videos/go-to-reference.mp4


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

# ---- Go to a reference with ctrl+g ------------------------------------------
Ctrl+G
Sleep 500ms
Type@430ms "ph"
Screenshot screenshots/showing-go-to-reference-modal.png
Sleep 1s
Enter
Sleep 550ms
Down@400ms 2
Tab
Sleep 550ms
Type@400ms "12"
Sleep 550ms
Enter

Sleep 5s

# ---- Go to a reference from the : command line ------------------------------
Type@330ms ":"
Sleep 1s
Type@430ms "mat"
Sleep 1s
Tab
Sleep 300ms
Type@450ms "5:"
Sleep 550ms
Screenshot screenshots/showing-go-to-reference-command.png
Type@300ms "5"
Enter
Sleep 5s


# ==== Teardown ===============================================================
Source ../teardown.tape
