---
doc_id: KB-0009
title: Access Denied on a Shared Network Folder
category: access
source: internal-runbook
tags: [permissions, shared folder, ntfs, group membership, access denied]
---

## Symptom
The user receives "You do not have permission to access this folder" when
opening a network share that colleagues can open.

## Cause
Either the user is not a member of the granting security group, or the group
membership was added but the user's Kerberos token has not been refreshed.

## Resolution
1. Confirm which security group grants access to the share and check the user's membership in Active Directory.
2. If membership was added recently, have the user sign out and sign back in so a new Kerberos token is issued.
3. Verify the effective permissions on the folder, checking both the share permissions and the NTFS permissions, as the more restrictive of the two applies.
4. Confirm no explicit Deny entry for the user or one of their groups exists on the folder.
5. Test access from a second machine to rule out a workstation-specific credential cache.

## Escalate if
The share holds regulated or restricted data, or the request requires adding a
user to a group they are not currently entitled to, which needs data-owner
approval.
