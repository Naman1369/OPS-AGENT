---
doc_id: KB-0014
title: Calendar Invitations Missing or Not Syncing Across Devices
category: email
source: internal-runbook
tags: [calendar, sync, invitation, mobile, delegate]
---

## Symptom
Meetings accepted on one device do not appear on another, or invitations never
reach the user's calendar.

## Cause
Duplicate calendar entries from a second sync source, a delegate processing
invitations before the user sees them, or a mobile client using a legacy
protocol that syncs only a limited window.

## Resolution
1. Confirm only one account on the device is syncing the calendar; remove duplicate account entries.
2. Check whether a delegate is configured to receive and process meeting requests on the user's behalf.
3. Verify the mobile client sync window is set to sync all calendar items rather than the default two-week window.
4. Have the user re-add the account on the mobile device using the modern authentication profile.
5. Confirm the invitation is not being filtered into Junk by checking the mail server message trace.

## Escalate if
Invitations are missing for an entire team or a room mailbox, which points to a
calendar processing configuration fault on the server.
