# ==== Output =================================================================
Output videos/feature-highlight.mp4


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

# ---- Highlight a verse ------------------------------------------------------
Type ":"
Sleep 800ms
Type@400ms "Isa"
Tab@800ms
Type "40"
Sleep 500ms
Tab@500ms
Type "10"
Sleep 800ms
Enter@500ms
Sleep 2s
Type "c"
Sleep 1s
Screenshot screenshots/showing-highlight-options.png
Type "1"
Sleep 1s
Screenshot screenshots/showing-highlighted-verse.png
Type "c"
Sleep 550ms
Down@500ms 3
Enter
Sleep 1s

# ---- Highlight a verse, unhighlight it, highlight it again ------------------
Ctrl+G
Type@330ms "ro"
Sleep 250ms
Tab
Type@200ms "10"
Sleep 175ms
Tab
Type@220ms "9"
Sleep 120ms
Enter
Sleep 1s
Type "c"
Sleep 550ms
Type "2"
Sleep 500ms
Type "c"
Down@130ms 6
Enter
Sleep 800ms
Type "c"
Sleep 450ms
Type "4"
Sleep 1s

# ---- Highlight several verses -----------------------------------------------
Type@300ms "hh"
Sleep 600ms
Type@450ms "/thes"
Enter
Escape
Sleep 300ms
Type@200ms "l"
Down@200ms 4
Type@200ms "l"
Down@100ms 15
Type@505ms "Vjj"
Sleep 400ms
Type@400ms "c6"
Enter
Sleep 1s

# ---- Show the highlights list and jump to one -------------------------------
Type "C"
Sleep 1s
Screenshot screenshots/showing-highlights-list.png
Type@330ms "jjjj"
Enter
Sleep 500ms
Type "C"
Sleep 400ms
Type@300ms "jj"
Enter
Sleep 5s


# ==== Teardown ===============================================================
Source ../teardown.tape
