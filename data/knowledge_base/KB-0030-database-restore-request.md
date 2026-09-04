---
doc_id: KB-0030
title: Request to Restore a Database or Overwritten Production Data
category: data_loss
source: internal-runbook
tags: [database, restore, backup, production, change control]
---

## Symptom
A team reports that production data has been overwritten, truncated, or
corrupted and requests a restore.

## Cause
Usually an erroneous bulk update or an unscoped delete executed against
production instead of a test environment.

## Resolution
1. Stop further writes to the affected tables immediately to preserve the recoverable state.
2. Record the exact time the erroneous operation ran, as point-in-time recovery depends on it.
3. Confirm the backup and transaction log retention covers the required recovery point.
4. Restore to a side-by-side copy first and validate the data before any production cutover.
5. Raise an emergency change record; production restores are never performed without one.

## Escalate if
Always. A production data restore is a change-controlled action requiring a
named human owner, a change record, and data-owner sign-off. This is never
resolved autonomously.
