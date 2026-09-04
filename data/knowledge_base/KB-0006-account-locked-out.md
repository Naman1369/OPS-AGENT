---
doc_id: KB-0006
title: Active Directory Account Repeatedly Locks Out
category: access
source: internal-runbook
tags: [active directory, account lockout, password, credentials, mobile]
---

## Symptom
The user's account locks within minutes of being unlocked, even when the user
is not actively typing a password.

## Cause
A cached stale password on a secondary device or service. The most frequent
sources are a mobile mail profile, a mapped network drive saved with old
credentials, and a scheduled task or service running as the user.

## Resolution
1. Identify the lockout source by reading Security event ID 4740 on the PDC emulator; the caller computer name field names the offending device.
2. Sign the user out of the corporate mail profile on all mobile devices and re-add the account with the current password.
3. Open Windows Credential Manager on the user's workstation and remove any stored credential holding the previous password.
4. Check for mapped drives and scheduled tasks configured with the user's explicit credentials and update them.
5. Unlock the account and monitor for a further lockout over the next fifteen minutes.

## Escalate if
Lockouts continue with no identifiable caller computer, or lockouts affect
several accounts at once, which may indicate a credential-stuffing attempt and
must be routed to the security team.
