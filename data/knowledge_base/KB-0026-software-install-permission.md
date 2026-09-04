---
doc_id: KB-0026
title: Software Installation Blocked by Insufficient Privileges
category: software
source: internal-runbook
tags: [installation, admin rights, software centre, licensing, approval]
---

## Symptom
The installer stops with an administrator rights prompt, or application control
blocks the executable from running.

## Cause
Standard users do not hold local administrator rights by policy. Approved
software is expected to be delivered through the managed software catalogue.

## Resolution
1. Check whether the requested application is available in the managed software catalogue and install it from there.
2. If the application is not in the catalogue, raise a software request so licensing and security review can be completed.
3. Confirm the user holds a licence for the application before installation is approved.
4. For a one-off approved installation, use the elevated deployment mechanism rather than granting the user standing administrator rights.
5. Record the approval reference on the ticket before installing.

## Escalate if
The user is requesting standing local administrator rights, or the software is
not on the approved list, both of which require a formal exception.
