-- usage: osascript en_setrecord.applescript LIBRARY_NAME RECNUM XML_FILE   (replaces that record's contents)
on run argv
	set libName to item 1 of argv
	set recNum to item 2 of argv
	set xmlText to read (POSIX file (item 3 of argv)) as «class utf8»
	tell application "EndNote 21"
		set ids to retrieve "all" records in document libName
		set dbAttr to text ((offset of "database=\"" in (item 1 of ids)) + 10) thru -1 of (item 1 of ids)
		set dbId to text 1 thru ((offset of "\"" in dbAttr) - 1) of dbAttr
		set record contents xmlText with ID ("<RecordID database=\"" & dbId & "\" recNum=\"" & recNum & "\" />")
	end tell
	return "set contents of #" & recNum & " in database " & dbId
end run
