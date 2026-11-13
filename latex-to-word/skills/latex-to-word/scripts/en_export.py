"""Export records from the open EndNote library as EndNote XML (read-only).

EndNote 21's AppleScript returns UTF-8 bytes mis-decoded as MacRoman; this undoes that.
usage: python3 en_export.py DB_INDEX OUT.xml ID [ID ...]
"""
import re, subprocess, sys

db, out, ids = sys.argv[1], sys.argv[2], sys.argv[3:]
spec = ", ".join('"<RecordID database=\\"%s\\" recNum=\\"%s\\" />"' % (db, i) for i in ids)
script = 'tell application "EndNote 21" to export {%s} as "RSXML"' % spec
raw = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=True).stdout


def unmangle(s):
    try:
        return s.encode("mac_roman").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        # fix runs of non-ASCII characters independently
        def fix(m):
            try:
                return m.group(0).encode("mac_roman").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                return m.group(0)
        return re.sub(r"[^\x00-\x7f]+", fix, s)


xml = unmangle(raw.strip())
open(out, "w", encoding="utf-8").write(xml)
print(len(re.findall(r"<record>", xml)), "records ->", out)
