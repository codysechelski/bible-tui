# ==== Output =================================================================
Output videos/overview.mp4


# ==== Settings ===============================================================
Source ../settings.tape


# ==== Setup ==================================================================
Source ../setup.tape


# ==== Steps ==================================================================
# ---- Open the app -----------------------------------------------------------
Sleep 500ms
Type@180ms "bible-tui"
Sleep 500ms
Enter
Sleep 1.5s

# ---- Move around with the arrow keys, then the same with Vim keys -----------
# Books: highlighting one previews it. Right moves on to its chapters, then into the text.
Down@400ms 3
Sleep 400ms
Right
Sleep 400ms
Down@350ms 2
Sleep 400ms
Right
Sleep 400ms
Down@300ms 3
Sleep 600ms
Type@250ms "jjj"
Sleep 300ms
Type@300ms "kk"
Sleep 1s

# ---- Jump to a reference with ctrl+g and mark it ----------------------------
Ctrl+G
Sleep 600ms
Type@200ms "rom"
Sleep 300ms
Tab
Type@250ms "8"
Sleep 300ms
Tab
Type@250ms "28"
Sleep 600ms
Enter
Sleep 1.2s
Type "m"
Sleep 1.5s

# ---- Fuzzy find a verse from a few words and highlight it -------------------
Ctrl+S
Sleep 800ms
Type@180ms "faith hope love"
Sleep 1s
Down@400ms 2
Up@400ms 2
Sleep 600ms
Enter
Sleep 1.2s
Type "c"
Sleep 1.2s
Type "1"
Sleep 1.5s

# ---- Fuzzy find another and mark it -----------------------------------------
Ctrl+S
Sleep 800ms
Type@180ms "lamp feet"
Sleep 1.2s
Enter
Sleep 1.2s
Type "m"
Sleep 1.5s

# ---- Find them again from the marks and highlights lists --------------------
# Newest first: Psalm 119:105, then Romans 8:28.
Type "M"
Sleep 1.5s
Type "j"
Sleep 800ms
Enter
Sleep 1.5s
Type "C"
Sleep 1.5s
Enter
Sleep 1.5s

# ---- Compare two versions side by side --------------------------------------
# The picker starts on the next version (the Bíblia Livre); one down is the KJV, which reads "charity"
# where the ASV reads "love".
Ctrl+W
Sleep 200ms
Type "v"
Sleep 1s
Type "j"
Sleep 600ms
Enter
Sleep 2.5s
# Both panes move together, and the highlight shows in both.
Type@350ms "kkk"
Sleep 600ms
Type@350ms "jjj"
Sleep 1.5s

# ---- A verse one version leaves out -----------------------------------------
# The ASV omits Matthew 17:21, so go to verse 20 (a reference has to exist in the ASV) and step down: the
# ASV pane is shaded where the KJV has verse 21.
Type ":"
Sleep 500ms
Type@200ms "matt"
Sleep 300ms
Tab
Type@250ms "17"
Sleep 300ms
Tab
Type@250ms "20"
Sleep 600ms
Enter
Sleep 1.5s
Type "j"
Sleep 5s


# ==== Teardown ===============================================================
Source ../teardown.tape
