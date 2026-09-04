---
doc_id: KB-0023
title: Windows Update Fails Repeatedly with an Installation Error
category: software
source: internal-runbook
tags: [windows update, patching, softwaredistribution, dism, sfc]
---

## Symptom
Updates download and then fail during installation, rolling back on restart and
reporting a hexadecimal error code.

## Cause
A corrupted update cache, insufficient free disk space, or component store
corruption.

## Resolution
1. Confirm at least fifteen gigabytes of free disk space before retrying, as staging requires substantial headroom.
2. Stop the Windows Update and Background Intelligent Transfer services, rename the SoftwareDistribution folder, then restart both services to force a clean cache.
3. Run DISM with the RestoreHealth option to repair the component store.
4. Run sfc /scannow after DISM completes and review the CBS log for unrepairable files.
5. Retry the update and record the new error code if it still fails.

## Escalate if
DISM cannot repair the component store, which usually means the device needs
re-imaging rather than further in-place repair.
