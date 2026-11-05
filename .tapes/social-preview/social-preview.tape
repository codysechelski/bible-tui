# The GitHub social preview. This tape has no video: it takes one screenshot, and produce-media composes it
# into docs/screenshots/social-preview.png with the words in card.json. Upload the result in the repo's
# Settings > General > Social preview; GitHub keeps its own copy.

# ==== Settings ===============================================================
Source ../settings.tape
# Twice the card's window, so the screenshot shrinks to it sharply.
Set Width 1360
Set Height 900
Set FontSize 16


# ==== Setup ==================================================================
Source ../setup.tape


# ==== Steps ==================================================================
Hide
Type "bible-tui"
Enter
Sleep 1.5s
Type ":1 John 4:5"
Sleep 500ms
Enter
Sleep 800ms
# The highlight picker on the current verse.
Type "c"
Sleep 800ms
Show
Sleep 300ms
Screenshot screenshots/terminal.png
Sleep 300ms


# ==== Teardown ===============================================================
Source ../teardown.tape
