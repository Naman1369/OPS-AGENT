---
doc_id: KB-0008
title: Multi-Factor Authentication Device Lost or Replaced
category: access
source: internal-runbook
tags: [mfa, 2fa, authenticator, enrollment, device replacement]
---

## Symptom
The user has a new phone or lost their previous device and can no longer
approve multi-factor prompts.

## Cause
Authenticator enrolments are bound to the device. Replacing the device requires
re-enrolment; the old registration remains active until removed.

## Resolution
1. Verify the user's identity through the approved out-of-band process before making any change to their authentication factors.
2. Remove the stale authenticator registration from the user's security information.
3. Issue a temporary access pass with a short validity window so the user can complete re-enrolment.
4. Guide the user through re-enrolling the authenticator application on the new device.
5. Confirm at least two recovery methods are registered before closing the ticket.

## Escalate if
The device was lost in circumstances suggesting theft or compromise, in which
case the security team must review recent sign-in activity.
