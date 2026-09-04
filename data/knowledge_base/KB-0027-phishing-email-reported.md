---
doc_id: KB-0027
title: User Reports a Suspected Phishing Email
category: security
source: internal-runbook
tags: [phishing, security, incident, reporting, credentials]
---

## Symptom
A user forwards or reports a message they believe is a phishing attempt, or
reports that they clicked a link or entered credentials on a suspicious page.

## Cause
Targeted or bulk phishing campaigns are routine. The response differs sharply
depending on whether the user interacted with the message.

## Resolution
1. Establish immediately whether the user clicked a link, opened an attachment, or entered credentials, and record the answer on the ticket.
2. If credentials were entered, treat this as a live security incident: reset the password, revoke active sessions, and notify the security team without delay.
3. Preserve the original message as evidence; do not delete it before the security team has collected the headers.
4. Submit the message through the report phishing mechanism so the mail gateway can act on it.
5. Advise the user of the outcome and reinforce the reporting process.

## Escalate if
Any interaction occurred, the message targeted several users, or it impersonates
an internal executive. All confirmed phishing incidents are owned by the
security team and are never closed autonomously.
