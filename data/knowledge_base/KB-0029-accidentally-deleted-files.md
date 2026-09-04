---
doc_id: KB-0029
title: User Reports Accidentally Deleted or Missing Files
category: data_loss
source: internal-runbook
tags: [data loss, deleted files, restore, version history, backup]
---

## Symptom
The user cannot find files they expect, or reports having deleted a folder they
still need.

## Cause
Files may be in the recycle bin, moved rather than deleted, restorable from
version history, or genuinely lost if the retention window has passed.

## Resolution
1. Establish the exact path, file names, and the approximate time of deletion before attempting any recovery.
2. Check the local recycle bin and the cloud storage recycle bin, which are separate locations with separate retention windows.
3. Use the previous versions or version history feature on the parent folder to restore the state before deletion.
4. For network shares, request a restore from the most recent snapshot that predates the deletion.
5. Confirm with the user that recovered content is complete before closing.

## Escalate if
The retention window has passed, the data is business critical, or the deletion
appears deliberate rather than accidental, all of which require a human owner.
