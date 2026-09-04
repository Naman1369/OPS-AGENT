---
doc_id: KB-0003
title: Wi-Fi Disconnects Intermittently on Laptops
category: network
source: internal-runbook
tags: [wifi, wireless, disconnect, power management, driver]
---

## Symptom
Wireless connectivity drops for five to thirty seconds at irregular intervals,
most often when the laptop is idle or running on battery.

## Cause
The dominant cause is the adapter's selective-suspend power-saving setting.
Secondary causes are outdated wireless drivers and roaming aggressiveness set
too low in environments with many access points.

## Resolution
1. Open Device Manager, select the wireless adapter, and on the Power Management tab clear "Allow the computer to turn off this device to save power".
2. Under the adapter's Advanced tab, set Roaming Aggressiveness to Medium-High and disable 802.11 power save mode.
3. Update the wireless adapter driver from the hardware vendor package, not the generic Windows Update driver.
4. In the active power plan, set Wireless Adapter Settings power saving mode to Maximum Performance on both battery and mains.
5. Forget and re-add the corporate SSID so the profile is rebuilt with current security settings.

## Escalate if
Multiple users in the same physical area report simultaneous drops, which
indicates an access point or controller fault for the network team.
