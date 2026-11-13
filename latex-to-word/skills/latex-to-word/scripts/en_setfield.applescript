-- usage: osascript en_setfield.applescript LIBRARY_NAME RECNUM FIELD VALUE_FILE(utf-8)
on run argv
	set libName to item 1 of argv
	set recNum to item 2 of argv
	set fieldName to item 3 of argv
	set val to read (POSIX file (item 4 of argv)) as «class utf8»
	tell application "EndNote 21"
		set ids to retrieve "all" records in document libName
		set dbAttr to text ((offset of "database=\"" in (item 1 of ids)) + 10) thru -1 of (item 1 of ids)
		set dbId to text 1 thru ((offset of "\"" in dbAttr) - 1) of dbAttr
		set field fieldName of record ("<RecordID database=\"" & dbId & "\" recNum=\"" & recNum & "\" />") to val
	end tell
	return "set " & fieldName & " of #" & recNum & " in database " & dbId
end run
