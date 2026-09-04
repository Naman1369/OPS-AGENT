---
doc_id: KB-0004
title: Internal Sites Unreachable but Internet Works (DNS Resolution Failure)
category: network
source: internal-runbook
tags: [dns, resolution, internal sites, nslookup, suffix]
---

## Symptom
Public websites load normally, but internal hostnames such as intranet or the
file server fail with "server not found". Connecting by IP address works.

## Cause
The client is using a public DNS resolver instead of the internal resolvers, or
the DNS suffix search list was lost, commonly after a VPN disconnect.

## Resolution
1. Run ipconfig /all and confirm the DNS servers listed are the internal resolvers, not a public resolver such as 8.8.8.8.
2. Run ipconfig /flushdns to clear a stale or poisoned client cache.
3. Test resolution explicitly with nslookup using the internal resolver as the server argument to separate client cache faults from resolver faults.
4. Confirm the connection-specific DNS suffix matches the corporate domain; re-apply it through the adapter's IPv4 advanced settings if it is missing.
5. Disconnect and reconnect the VPN so the tunnel re-pushes DNS configuration to the adapter.

## Escalate if
The internal resolvers do not answer queries from any client, which is a
resolver-side outage and must go to the network team immediately.
