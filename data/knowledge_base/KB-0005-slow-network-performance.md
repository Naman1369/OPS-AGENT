---
doc_id: KB-0005
title: Slow Network Performance and High Latency on a Single Workstation
category: network
source: internal-runbook
tags: [latency, slow, bandwidth, duplex, proxy]
---

## Symptom
One workstation experiences slow file transfers and high latency while adjacent
machines on the same switch perform normally.

## Cause
Most often a duplex mismatch on the wired link, a saturated background sync
client, or traffic being forced through a distant proxy.

## Resolution
1. Run a ping to the default gateway and record the latency and any packet loss to separate local link faults from upstream faults.
2. Check the adapter link speed and duplex; set both switch port and adapter to auto-negotiate rather than a forced value.
3. Review Resource Monitor for a background process saturating the link, commonly a cloud sync client performing a first-time full sync.
4. Confirm the proxy configuration resolves to the nearest regional proxy and not a remote one.
5. Replace the patch cable and test a different wall port to rule out physical layer faults.

## Escalate if
Latency to the gateway is consistently above fifty milliseconds or packet loss
exceeds one percent, which points to switch or uplink congestion.
