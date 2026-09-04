---
doc_id: KB-0022
title: Spreadsheet Reports "Locked for Editing by Another User"
category: software
source: internal-runbook
tags: [excel, file lock, shared file, owner file, read-only]
---

## Symptom
Opening a shared spreadsheet offers read-only access and names another user, or
names the current user, as holding the lock.

## Cause
A stale lock owner file left behind when a previous session ended abnormally,
or a genuine concurrent edit by another user.

## Resolution
1. Confirm with the named user whether the file is genuinely open before taking any action.
2. If the lock is stale, locate and remove the hidden owner file that begins with a tilde and dollar prefix in the same folder.
3. Check the file server open-files list and close the stale handle if the lock persists.
4. Advise the user to close the file properly rather than closing the application window while a save is in progress.
5. For files edited by several people regularly, move the file to a location that supports co-authoring.

## Escalate if
The stale handle cannot be cleared from the file server, which requires the
storage administrators.
