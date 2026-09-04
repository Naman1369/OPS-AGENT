---
doc_id: KB-0007
title: Password Reset and Self-Service Password Recovery
category: access
source: internal-runbook
tags: [password, reset, self-service, sspr, expiry]
---

## Symptom
The user cannot sign in and reports that the password is expired, forgotten, or
was rejected after a recent change.

## Cause
Routine expiry under the ninety-day policy, or an unsynchronised password
change that has not yet replicated to all domain controllers.

## Resolution
1. Direct the user to the self-service password reset portal and confirm their registered recovery methods are current.
2. If self-service fails, verify the user's identity against the approved verification questions before any manual reset.
3. Perform the reset and set the account to require a password change at next sign-in.
4. Ask the user to sign in on a domain-connected machine first so that cached credentials are refreshed before they use the VPN.
5. Confirm the new password satisfies the complexity policy of twelve characters with mixed case, a digit and a symbol.

## Escalate if
Identity cannot be verified through the approved process, or the request
concerns a privileged or service account, which requires a change record.
