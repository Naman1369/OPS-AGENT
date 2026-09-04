---
doc_id: KB-0021
title: Desktop Application Crashes Immediately on Launch
category: software
source: internal-runbook
tags: [crash, application, event viewer, profile, reinstall]
---

## Symptom
The application window appears briefly and closes, or never appears. An
application error is recorded in the Windows Application event log.

## Cause
A corrupted user configuration, a conflicting add-in, or a failed update that
left the installation in a mixed state.

## Resolution
1. Open Event Viewer and read the Application log entry for the crash, recording the faulting module name.
2. Launch the application with a clean profile or in safe mode where supported to determine whether the fault is user-specific.
3. Rename the application's user configuration folder in AppData so a fresh configuration is generated on next launch.
4. Run the installer's repair option before attempting a full reinstall.
5. If the faulting module belongs to a third-party add-in, disable that add-in and retest.

## Escalate if
The faulting module is a system library or the crash appears across many
workstations after a deployment, which indicates a packaging fault.
