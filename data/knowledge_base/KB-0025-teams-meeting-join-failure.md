---
doc_id: KB-0025
title: Cannot Join Meetings from the Collaboration Client
category: software
source: internal-runbook
tags: [teams, meeting, join failure, cache, proxy]
---

## Symptom
Clicking a meeting link opens the client but the join attempt fails or hangs on
connecting. Joining from the browser works.

## Cause
A corrupted client cache, an outdated client version, or media traffic being
blocked by the proxy or firewall.

## Resolution
1. Sign out of the client, clear the client cache directory, and sign back in.
2. Update the client to the current version, as older builds are blocked from joining after a service update.
3. Confirm the required media ports are permitted and that media traffic bypasses the proxy per the vendor's network guidance.
4. Test joining from the browser client to determine whether the fault is the desktop client or the network path.
5. Reset the client's stored credentials if the sign-in state appears stale.

## Escalate if
Browser join also fails from multiple networks, which indicates a service-side
issue rather than a client fault.
