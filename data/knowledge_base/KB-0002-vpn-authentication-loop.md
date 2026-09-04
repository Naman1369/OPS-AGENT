---
doc_id: KB-0002
title: VPN Client Repeatedly Prompts for Credentials (Authentication Loop)
category: network
source: internal-runbook
tags: [vpn, authentication, mfa, credentials, remote access]
---

## Symptom
The VPN client accepts the username and password, then immediately re-prompts.
No error code is shown. The user can sign in to web applications normally.

## Cause
Usually a stale cached credential in Windows Credential Manager, an expired
machine certificate, or an MFA push that timed out before the user approved it.

## Resolution
1. Open Windows Credential Manager and delete any saved generic credential whose name begins with the VPN gateway hostname.
2. Confirm the user's MFA device is enrolled and reachable, and ask the user to approve the push within thirty seconds of connecting.
3. Check the machine certificate expiry in the Local Computer certificate store under Personal; renew through the internal CA if it expires within thirty days.
4. Clear the VPN client cache directory and relaunch the client as the signed-in user, not as administrator.
5. Verify the account is not in a disabled or password-expired state in Active Directory.

## Escalate if
The account is locked at the directory level, the certificate authority is
unreachable, or the loop persists after credential and certificate refresh.
