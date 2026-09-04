---
doc_id: KB-0013
title: Shared Mailbox Not Visible or Read-Only for a Delegate
category: email
source: internal-runbook
tags: [shared mailbox, delegate, permissions, send as, full access]
---

## Symptom
A newly granted shared mailbox does not appear in the user's Outlook folder
list, or appears but rejects attempts to send from that address.

## Cause
Automapping takes time to propagate, and Full Access permission does not by
itself grant the right to send as the mailbox.

## Resolution
1. Confirm the user has been granted Full Access permission on the shared mailbox.
2. Grant Send As or Send on Behalf separately, depending on whether the recipient should see the shared address or the delegate's name.
3. Allow up to sixty minutes for automapping to propagate, then restart Outlook.
4. If the mailbox still does not appear, add it manually as an additional mailbox under the account's advanced settings.
5. Verify the sender address by sending a test message to an internal recipient and checking the displayed From address.

## Escalate if
The permission grant requires approval from the mailbox owner or the data owner
and that approval has not been recorded.
