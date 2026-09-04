---
doc_id: KB-0024
title: Browser Shows a Certificate Warning on an Internal Site
category: software
source: internal-runbook
tags: [certificate, browser, ssl, trust store, clock skew]
---

## Symptom
The browser blocks an internal site with a certificate error such as
"Your connection is not private" or a name mismatch warning.

## Cause
The internal certificate authority root is missing from the machine trust
store, the site certificate has expired, or the system clock is skewed.

## Resolution
1. Read the specific certificate error rather than the generic warning; a name mismatch, an expiry and an untrusted issuer each have different fixes.
2. Confirm the system clock and time zone are correct, as clock skew invalidates otherwise valid certificates.
3. Verify the internal root certificate is present in the machine Trusted Root Certification Authorities store and re-deploy it through group policy if missing.
4. Check the certificate expiry date on the site and raise a renewal request if it has passed.
5. Clear the browser's SSL state and retest in a private window.

## Escalate if
The site certificate has genuinely expired, which needs the service owner to
renew it, or if the warning appears on an external site, which may indicate
interception and should go to the security team.
