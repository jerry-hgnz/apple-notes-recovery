from __future__ import annotations

import subprocess


def run_osascript(script: str, *args: str) -> str:
    proc = subprocess.run(
        ["osascript", "-", *args],
        input=script,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "osascript failed").strip())
    return (proc.stdout or "").strip()


EXPORT_ACCOUNT_FOLDERS_SCRIPT = r'''
on replaceText(findText, replaceText, sourceText)
	set AppleScript's text item delimiters to findText
	set textItems to every text item of sourceText
	set AppleScript's text item delimiters to replaceText
	set sourceText to textItems as text
	set AppleScript's text item delimiters to ""
	return sourceText
end replaceText

on sanitizeText(sourceText)
	set s to sourceText as text
	set s to my replaceText(tab, " ", s)
	set s to my replaceText(return, " ", s)
	set s to my replaceText(linefeed, " ", s)
	return s
end sanitizeText

on joinLines(lineList)
	set oldTID to AppleScript's text item delimiters
	set AppleScript's text item delimiters to linefeed
	set outputText to lineList as text
	set AppleScript's text item delimiters to oldTID
	return outputText
end joinLines

on run argv
	set accountName to item 1 of argv
	set outLines to {}
	tell application "Notes"
		tell account accountName
			repeat with f in folders
				copy my sanitizeText(name of f) to end of outLines
			end repeat
		end tell
	end tell
	return my joinLines(outLines)
end run
'''


EXPORT_FOLDER_NOTES_SCRIPT = r'''
on replaceText(findText, replaceText, sourceText)
	set AppleScript's text item delimiters to findText
	set textItems to every text item of sourceText
	set AppleScript's text item delimiters to replaceText
	set sourceText to textItems as text
	set AppleScript's text item delimiters to ""
	return sourceText
end replaceText

on sanitizeText(sourceText)
	set s to sourceText as text
	set s to my replaceText(tab, " ", s)
	set s to my replaceText(return, " ", s)
	set s to my replaceText(linefeed, " ", s)
	return s
end sanitizeText

on joinLines(lineList)
	set oldTID to AppleScript's text item delimiters
	set AppleScript's text item delimiters to linefeed
	set outputText to lineList as text
	set AppleScript's text item delimiters to oldTID
	return outputText
end joinLines

on run argv
	set accountName to item 1 of argv
	set folderName to item 2 of argv
	set outLines to {}
	tell application "Notes"
		tell account accountName
			if not (exists folder folderName) then error "Folder not found: " & folderName
			repeat with n in notes of folder folderName
				set noteID to id of n
				set noteTitle to my sanitizeText(name of n)
				set modText to my sanitizeText((modification date of n) as text)
				copy (noteID & tab & noteTitle & tab & modText) to end of outLines
			end repeat
		end tell
	end tell
	return my joinLines(outLines)
end run
'''


MOVE_NOTE_SCRIPT = r'''
on run argv
	set accountName to item 1 of argv
	set noteID to item 2 of argv
	set targetFolderName to item 3 of argv
	tell application "Notes"
		tell account accountName
			try
				set targetFolder to folder targetFolderName
			on error
				set targetFolder to make new folder with properties {name:targetFolderName}
			end try
			move (note id noteID) to targetFolder
			return "OK"
		end tell
	end tell
end run
'''


def export_account_folders(account: str) -> list[str]:
    raw = run_osascript(EXPORT_ACCOUNT_FOLDERS_SCRIPT, account)
    return [line.strip() for line in raw.splitlines() if line.strip()]


def export_folder_notes(account: str, folder: str) -> list[dict[str, str]]:
    raw = run_osascript(EXPORT_FOLDER_NOTES_SCRIPT, account, folder)
    rows: list[dict[str, str]] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        note_id = parts[0] if len(parts) > 0 else ""
        title = parts[1] if len(parts) > 1 else ""
        modification_date = parts[2] if len(parts) > 2 else ""
        rows.append(
            {
                "note_id": note_id,
                "title": title,
                "modification_date": modification_date,
            }
        )
    return rows


def move_note(account: str, note_id: str, target_folder: str) -> tuple[bool, str]:
    proc = subprocess.run(
        ["osascript", "-", account, note_id, target_folder],
        input=MOVE_NOTE_SCRIPT,
        text=True,
        capture_output=True,
    )
    if proc.returncode == 0:
        return True, (proc.stdout or "").strip()
    return False, (proc.stderr or proc.stdout or "").strip()
