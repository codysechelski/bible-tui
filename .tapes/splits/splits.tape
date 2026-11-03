# ==== Output =================================================================
Output videos/splits.mp4


# ==== Settings ===============================================================
Source ../settings.tape


# ==== Setup ==================================================================
Source ../setup.tape


# ==== Steps ==================================================================
# ---- Open the app -----------------------------------------------------------
Sleep 500ms
Type@220ms "bible-tui kjv"
Sleep 500ms
Enter
Sleep 1s

# ---- Go to John 3:16 --------------------------------------------------------
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
Sleep 1s

# ---- Split with ctrl+w v, then close the split with ctrl+w q ----------------
Ctrl+W
Sleep 100ms
Type "v"
Screenshot screenshots/showing-new-pane-version-picker.png
Sleep 1s
Enter
Screenshot screenshots/showing-vertical-split.png
Sleep 500ms
Type@330ms "jjjjkkk"
Sleep 550ms
Type@250ms ":romans 10:9"
Enter
Sleep 2s
Type@200ms "kkkkjj"
Ctrl+W
Sleep 100ms
Type "q"
Sleep 1s

# ---- Split with :split, switch panes with ctrl+w w, close it with :only ------
Type@350ms ":spl"
Sleep 400ms
Enter
Sleep 500ms
Type "j"
Enter
# The new pane is the Bíblia Livre, until :only closes it.
#@ footnote bible-livre
Sleep 400ms
Screenshot screenshots/showing-horizontal-split.png
Type@250ms "kkkjjjj"
Sleep 450ms
Ctrl+W
Sleep 120ms
Type "w"
Sleep 1s
Type@330ms ":on"
Sleep 500ms
Enter
#@ footnote off
Sleep 5s


# ==== Teardown ===============================================================
Source ../teardown.tape
