# Shared teardown for every tape in this folder. Each tape sources this at the very end:
#   Source ../teardown.tape
#
# Quits bible-tui if it's still open, then restores the real app home that setup.tape backed up.
Hide
Escape
Type ":q"
Enter
Sleep 500ms
# Clear anything left on the shell's command line (":q" at a shell prompt is just an error).
Ctrl+C
Type "../app-home restore"
Enter
Sleep 500ms
