---
doc_id: KB-0012
title: Outbound Email Stuck in Outbox or Rejected on Send
category: email
source: internal-runbook
tags: [email, smtp, outbox, send failure, attachment, quota]
---

## Symptom
Messages remain in the Outbox or bounce back with a delivery failure notice.
Incoming mail arrives normally.

## Cause
Common causes are an oversized attachment, a mailbox at its sending quota, an
invalid recipient address, or a stuck message blocking the send queue.

## Resolution
1. Check the attachment size against the twenty-five megabyte send limit and replace large attachments with a share link.
2. Open the Outbox, move the stuck message to Drafts, and confirm whether the remaining queue then flushes.
3. Read the non-delivery report code; a 5.1.1 indicates an unknown recipient and a 5.7.1 indicates a policy or permission rejection.
4. Verify the mailbox is below quota, as a full mailbox blocks sending as well as receiving.
5. Confirm the send-as permission if the user is sending from a shared or delegate mailbox.

## Escalate if
The non-delivery report indicates the message was blocked by a transport rule or
by the anti-spam gateway, which requires the mail administrators to review.
