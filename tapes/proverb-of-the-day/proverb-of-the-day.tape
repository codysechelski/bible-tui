# ==== Output =================================================================
Output videos/proverb-of-the-day.mp4


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
Sleep 1.5s

# ---- :potd goes to the chapter of Proverbs for today's date ----------------
Type ":"
Sleep 600ms
Type@300ms "potd"
Sleep 1s
Enter
Sleep 1.5s
Screenshot screenshots/showing-proverb-of-the-day.png
Sleep 1.5s
Type@250ms "jjjj"
Sleep 2s

# ---- Step back a chapter, then run it from the commands list ---------------
Type "["
Sleep 1.5s
Type "?"
Sleep 1s
# "proverb of the day" is the 17th command.
Type@120ms "jjjjjjjjjjjjjjjj"
Sleep 1.5s
Enter
Sleep 4s


# ==== Teardown ===============================================================
Source ../teardown.tape
