---
doc_id: KB-0016
title: Laptop Does Not Power On or Shows No Display
category: hardware
source: internal-runbook
tags: [laptop, power, no display, battery, hardware failure]
---

## Symptom
Pressing the power button produces no lights, no fan noise, or lights without
any display output.

## Cause
Either a depleted battery with a faulty charger, a residual power state that
needs draining, or a genuine mainboard or display failure.

## Resolution
1. Connect a known-good charger and confirm the charging indicator illuminates; leave it connected for at least fifteen minutes before testing.
2. Perform a power drain: disconnect the charger, hold the power button for thirty seconds, then reconnect and power on.
3. Connect an external monitor to determine whether the fault is the display panel or the system itself.
4. Listen for beep codes or observe diagnostic light patterns and match them against the vendor's diagnostic table.
5. Run the vendor's built-in pre-boot hardware diagnostic and record the resulting error code.

## Escalate if
The diagnostic reports a mainboard, memory or storage fault, which requires a
hardware replacement under the warranty process rather than a software fix.
