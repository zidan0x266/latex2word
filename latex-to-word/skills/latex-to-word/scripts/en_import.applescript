-- usage: osascript en_import.applescript XML_FILE LIBRARY_NAME
on run argv
	set xmlText to read (POSIX file (item 1 of argv)) as «class utf8»
	tell application "EndNote 21"
		set result to import {xmlText} into document (item 2 of argv)
	end tell
	return "ok"
end run
