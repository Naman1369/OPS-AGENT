---
doc_id: KB-0020
title: Laptop Battery Drains Rapidly or Reports Reduced Capacity
category: hardware
source: internal-runbook
tags: [battery, power, capacity, battery report, replacement]
---

## Symptom
Battery runtime has fallen noticeably, or the operating system warns that the
battery needs replacement.

## Cause
Normal chemical wear after several hundred charge cycles, a background process
preventing sleep, or a stale power plan configuration.

## Resolution
1. Generate a battery report with powercfg /batteryreport and compare the full charge capacity against the design capacity.
2. Treat a full charge capacity below seventy percent of design capacity as end of life and raise a hardware replacement request.
3. Run powercfg /energy to identify processes preventing the system from entering low power states.
4. Reset the active power plan to the corporate balanced default to clear any manual overrides.
5. Update the system firmware, as battery calibration logic is delivered through firmware updates.

## Escalate if
The battery is swollen or the device is unusually hot, which is a safety issue
requiring the device to be taken out of service immediately.
