# ==== Output =================================================================
Output videos/navigation.mp4


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

# ---- Switch between Bible and alphabetical book order -----------------------
Screenshot screenshots/showing-books-in-bible-order.png
Type "a"
Screenshot screenshots/showing-books-in-alphabetical-order.png
Sleep 2s
Down@420ms 5
Up@450ms 5
Sleep 550ms
Type "a"
Sleep 2s

# ---- Move with the arrow keys -----------------------------------------------
Down@330ms 10
Up@300ms 4
Right@150ms
Down@400ms 7
Up@300ms 6
Right@100ms
Down@120ms 6
Up@120ms 5
Left@140ms 2
Sleep 1s

# ---- Move with hjkl, G/gg, and ctrl+u/ctrl+d --------------------------------
Type@400ms "G"
Sleep 1s
Ctrl+U
Sleep 430ms
Ctrl+U
Sleep 430ms
Ctrl+U
Sleep 430ms
Ctrl+D
Sleep 440ms
Ctrl+D
Sleep 440ms
Type@430ms "gg"
Sleep 1s
Type@300ms "jjjjj"
Type@250ms "kkkk"
Type@120ms "l"
Type@200ms "jjjjjj"
Type@190ms "kk"
Type@130ms "l"
Type@303ms "jjj"
Type@300ms "kkk"
Type@400ms "G"
Sleep 1s
Type@300ms "gg"
Sleep 1s
Ctrl+D
Sleep 440ms
Ctrl+D
Sleep 440ms
Ctrl+D
Sleep 540ms
Ctrl+U
Sleep 430ms
Ctrl+U
Sleep 2.53s

# ---- Step through chapters with ] and [ -------------------------------------
Type@400ms "hhgg"
Sleep 400ms
Type@330ms "jjjjjjj"
Sleep 500ms
Type@550ms "]]]]]"
Sleep 300ms
Type@600ms "[[[["
Sleep 5s


# ==== Teardown ===============================================================
Source ../teardown.tape
