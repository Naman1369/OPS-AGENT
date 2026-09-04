---
doc_id: KB-0010
title: Single Sign-On Fails for a Specific Application
category: access
source: internal-runbook
tags: [sso, saml, application, identity provider, assertion]
---

## Symptom
The user signs in to the identity provider successfully but the target
application rejects the session or returns to the login page in a loop.

## Cause
A SAML assertion mismatch, an expired signing certificate on the service
provider side, or the user not being assigned to the application.

## Resolution
1. Confirm the user is assigned to the application in the identity provider and holds the required application role.
2. Check the service provider signing certificate expiry; renew and re-upload before expiry if it falls within thirty days.
3. Compare the assertion attributes the application expects against what the identity provider is sending, in particular the name identifier format.
4. Have the user clear cookies for both the application and identity provider domains, then retry in a private browsing window.
5. Review the identity provider sign-in logs for the specific failure reason rather than relying on the browser message.

## Escalate if
The signing certificate has already expired, or the failure affects all users of
the application, which is a service-level fault requiring the application owner.
