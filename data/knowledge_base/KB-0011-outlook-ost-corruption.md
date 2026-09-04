---
doc_id: KB-0011
title: Outlook Will Not Start or Hangs on "Loading Profile" (OST Corruption)
category: email
source: internal-runbook
tags: [outlook, ost, profile, corruption, cached exchange mode]
---

## Symptom
Outlook hangs on the loading profile splash screen, or opens and then reports
"Cannot open your default e-mail folders". Webmail works normally.

## Cause
A corrupted offline data file, an add-in blocking start-up, or a damaged Outlook
profile. The webmail check confirms the mailbox itself is healthy.

## Resolution
1. Start Outlook in safe mode with outlook.exe /safe; if it starts cleanly, disable add-ins one at a time to find the offending add-in.
2. Close Outlook and rename the OST file in the local AppData Outlook folder; Outlook rebuilds it on next start from the server copy.
3. If rebuilding does not help, create a new Outlook mail profile in the Mail control panel and set it as the default profile.
4. Confirm the mailbox size is within quota, as a mailbox at or over quota can stall the initial synchronisation.
5. Allow the initial cached-mode synchronisation to complete before judging the fix; on a large mailbox this can take an hour.

## Escalate if
The mailbox is inaccessible from webmail as well, which indicates a mailbox
server or database fault rather than a client fault.
