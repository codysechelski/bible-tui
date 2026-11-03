# Shared setup for every tape in this folder. Each tape sources this right after settings.tape:
#   Source ../setup.tape
#
# Backs up the real bible-tui app home and swaps in a clean one (defaults/config.json, ASV open, no marks
# or highlights). teardown.tape puts the real one back. Any tape-specific setup goes after this.
Hide
Type "../app-home setup"
Enter
Type "clear"
Enter
Sleep 500ms
Show
