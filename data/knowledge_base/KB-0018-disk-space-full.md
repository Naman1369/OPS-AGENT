---
doc_id: KB-0018
title: Low Disk Space Warnings and Failure to Save Files
category: hardware
source: internal-runbook
tags: [disk space, storage, cleanup, temp files, onedrive]
---

## Symptom
The user receives low disk space warnings, applications fail to save, and
Windows updates fail to install.

## Cause
Accumulated temporary files, Windows update servicing files, a large local
cache from a cloud sync client, or an oversized local mail data file.

## Resolution
1. Run Disk Cleanup with the clean up system files option and remove previous Windows installation files and delivery optimisation files.
2. Enable Files On-Demand in the cloud sync client so rarely used files are stored online rather than locally.
3. Locate large local mail data files and confirm they are within the supported size for the mailbox configuration.
4. Clear the user profile temp folder and browser caches.
5. Confirm at least fifteen percent free space remains after cleanup, as the drive needs headroom for updates and paging.

## Escalate if
The drive fills again within days without a clear cause, which may indicate a
runaway log file or an application fault requiring investigation.
