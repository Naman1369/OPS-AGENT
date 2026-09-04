---
doc_id: KB-0001
title: VPN Connection Fails with Error 809 (L2TP/IPsec behind NAT)
category: network
source: internal-runbook
tags: [vpn, error 809, l2tp, ipsec, nat, remote access]
---

## Symptom
The Windows built-in VPN client fails to establish a tunnel and reports
"Error 809: The network connection between your computer and the VPN server
could not be established because the remote server is not responding."
Typically seen from home routers, hotel Wi-Fi and mobile hotspots.

## Cause
Error 809 is a NAT traversal failure. L2TP/IPsec requires UDP 500 and UDP 4500.
Windows disables NAT-T for connections behind a NAT device by default, and many
consumer routers or captive-portal networks additionally block those ports.

## Resolution
1. Confirm the user is not on a captive-portal network that blocks UDP 500 and UDP 4500; test the same VPN profile on a mobile hotspot to isolate the network.
2. Enable NAT traversal on the client: create the DWORD registry value AssumeUDPEncapsulationContextOnSendRule under HKLM\SYSTEM\CurrentControlSet\Services\PolicyAgent and set it to 2.
3. Reboot the workstation; the PolicyAgent service reads this value only at start-up.
4. Verify the VPN profile type is set to "L2TP/IPsec with pre-shared key" and that the pre-shared key matches the current gateway value.
5. Restart the IKE and AuthIP IPsec Keying Modules service and retry the connection.
6. If the tunnel still fails, capture the client-side event log entries from Applications and Services Logs and attach them to the ticket.

## Escalate if
The registry change and reboot do not resolve the failure, the VPN gateway is
rejecting the pre-shared key, or more than three users report Error 809 in the
same hour, which indicates a gateway-side fault rather than a client fault.
