# ==== Output =================================================================
Output videos/searching.mp4


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

# ---- Search the books pane, step through matches with n and N ---------------
Type "/"
Sleep 400ms
Type@330ms "john"
Screenshot screenshots/showing-search-in-books.png
Sleep 400ms
Enter
Sleep 500ms
Type@300ms "nnn"
Sleep 1s
Type@330ms "NNN"
Sleep 330ms
Enter

# ---- Search the text pane ---------------------------------------------------
Sleep 1s
Type "l"
Sleep 1s
Type "/"
Sleep 333ms
Type@500ms "baptize"
Screenshot screenshots/showing-search-in-verses.png
Sleep 330ms
Enter
Sleep 400ms
Type@300ms "nnnn"
Sleep 1s
Type@330ms "NNNN"
Sleep 330ms
Escape
Sleep 5s


# ==== Teardown ===============================================================
Source ../teardown.tape
