---
doc_id: KB-0017
title: External Monitors Not Detected Through a Docking Station
category: hardware
source: internal-runbook
tags: [docking station, monitor, display, usb-c, firmware]
---

## Symptom
Monitors connected through the dock are not detected, or only one of two
monitors works, while direct connection to the laptop works normally.

## Cause
Outdated dock firmware, an underpowered or non-compliant USB-C cable, or
display link bandwidth exhausted at the configured resolution and refresh rate.

## Resolution
1. Power-cycle the dock by disconnecting it from mains power for thirty seconds, not just from the laptop.
2. Update the docking station firmware using the vendor utility with the dock connected to mains power throughout.
3. Confirm the USB-C cable is the one supplied with the dock and supports both power delivery and display alternate mode.
4. Reduce the refresh rate on both monitors to sixty hertz to stay within the dock's bandwidth budget.
5. Update the graphics driver from the laptop vendor's package rather than the generic chipset driver.

## Escalate if
The dock fails on a second laptop with a known-good cable, indicating a faulty
dock that should be replaced.
