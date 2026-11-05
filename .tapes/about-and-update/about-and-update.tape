# ==== Output =================================================================
Output videos/about-and-update.mp4


# ==== Settings ===============================================================
Source ../settings.tape


# ==== Setup ==================================================================
Source ../setup.tape

# A throwaway HOME where bible-tui is a git clone one release behind (see setup.sh).
Hide
Type "../sandbox about-and-update ./setup.sh"
Enter
Sleep 2s
Type "clear"
Enter
Sleep 500ms
Show


# ==== Steps ==================================================================
# ---- Open the app: the footer says a new release is out -------------------
Sleep 500ms
Type@120ms "bible-tui"
Sleep 400ms
Enter
Sleep 2.5s
Screenshot screenshots/showing-update-notice.png

# ---- Go to a verse ---------------------------------------------------------
Ctrl+G
Sleep 400ms
Type@200ms "rom"
Tab
Type@200ms "8"
Tab
Type@200ms "28"
Sleep 500ms
Enter
Sleep 1.5s

# ---- :about shows the version and the newer release -----------------------
Type ":"
Sleep 400ms
Type@250ms "about"
Sleep 600ms
Enter
Sleep 2s
Screenshot screenshots/showing-about.png
Sleep 1s
Escape
Sleep 800ms

# ---- :update installs it and reopens at Romans 8:28 -----------------------
Type ":"
Sleep 400ms
Type@250ms "update"
Sleep 600ms
Enter
Sleep 3s
Screenshot screenshots/showing-updated.png
Sleep 1.5s

# ---- :about again: up to date ----------------------------------------------
Type ":"
Sleep 400ms
Type@250ms "about"
Sleep 400ms
Enter
Sleep 2.5s
Escape
Sleep 3s


# ==== Teardown ===============================================================
# Leave the sandbox shell, then the shared teardown in the tape's own shell.
Hide
Escape
Type ":q"
Enter
Sleep 500ms
Type "exit"
Enter
Sleep 500ms
Source ../teardown.tape
