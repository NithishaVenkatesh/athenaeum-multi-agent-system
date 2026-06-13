---
kind: module
id: cb-c03-m01
vertical: cloud-backend
course_id: cb-c03
title: Authentication with the Microsoft identity platform
level: advanced
grounded_on: "AZ-204 skills outline (2026-01-14), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-204
synthetic: true
order: 1
prereqs: [cb-c01, cb-c02]
objectives:
  - Authenticate users with the Microsoft identity platform
  - Authorize apps using Microsoft Entra ID
  - Call Microsoft Graph on behalf of a signed-in user
---

# Authentication with the Microsoft identity platform

Imagine you are building the internal expense portal for a fictional firm, Northwind Logistics. The portal needs to show each employee *their own* travel claims, let a manager approve their team's claims, and read each user's calendar to pre-fill trip dates. You cannot ask people to invent yet another password, and you certainly cannot store one. You need the portal to trust the company's existing directory, prove who the caller is, and then act with exactly the permissions that user has granted — no more. That is the job of the Microsoft identity platform, and getting its mental model right is the difference between an app that is secure by construction and one that is a breach waiting to happen.

## Learning objectives

By the end of this module you will be able to:

- Register an application in Microsoft Entra ID and reason about its identity (client ID, tenant, secrets, redirect URIs).
- Authenticate a user and acquire tokens using the appropriate OAuth 2.0 / OpenID Connect flow.
- Distinguish delegated permissions from application permissions and choose the right one.
- Acquire an access token and call Microsoft Graph on behalf of a signed-in user with MSAL.

## Concepts

### Tokens, not passwords: how the platform proves identity

The Microsoft identity platform is Microsoft Entra ID's implementation of two open standards: **OpenID Connect** (for *authentication* — proving who a user is) and **OAuth 2.0** (for *authorization* — granting an app limited access to a resource). The unit of currency is the **token**, a signed JSON Web Token (JWT) that an app presents instead of a credential.

There are two tokens you care about. An **ID token** answers "who signed in?" and is consumed by your app to establish a session. An **access token** answers "what is this caller allowed to do against a specific resource?" and is sent to an API like Microsoft Graph in the `Authorization: Bearer` header. The resource validates the token's signature, issuer, audience, and expiry — it never sees a password. Because tokens are signed by Entra ID and scoped to a single audience, a token minted for one API is useless against another.

The flow you reach for depends on the app type. A server-side web app uses the **authorization code flow**: the browser is redirected to Entra ID, the user signs in, an authorization *code* comes back to your redirect URI, and your server exchanges that code (plus a client secret or certificate) for tokens. A single-page or mobile app uses the same flow hardened with **PKCE** so no secret is needed. A daemon with no user uses the **client credentials flow**. Picking the wrong flow is the most common architectural mistake here, so anchor on: *is there a human in the loop?*

### App registration: your application's own identity

Before any of this works, the app must exist in the directory. An **app registration** in Entra ID gives your application a **client ID** (its public username), a **tenant** it belongs to, one or more **redirect URIs** where tokens may be returned, and a set of **credentials** — either a client secret or, preferably, a certificate or federated credential. The registration also declares the **API permissions** the app wants.

A subtle but load-bearing distinction lives here. **Delegated permissions** mean the app acts *as the signed-in user* and can do only what that user is allowed to do — `Calendars.Read` delegated lets the app read the calendar of whoever is logged in. **Application permissions** mean the app acts *as itself* with no user, typically for daemons, and are far more powerful because they apply tenant-wide. Application permissions usually require an administrator to consent. When you only need a user's own data, always choose delegated; it is the principle of least privilege made concrete.

### Microsoft Graph: one API for the Microsoft cloud

Microsoft Graph is the unified REST API for Microsoft 365 data — users, groups, calendars, mail, files, Teams. You authenticate once against the identity platform and then call `https://graph.microsoft.com/v1.0/...` with the access token. The scopes you request on the token (for example `User.Read`, `Calendars.Read`) determine which Graph endpoints succeed. The mental model: the *scope* on the token and the *permission* on the registration must line up, and the user (or admin) must have consented. If a Graph call returns `403`, the cause is almost always a missing or unconsented scope, not a bug in your code.

## Walkthrough: signing in a Northwind employee and reading their calendar

You will build the token-acquisition core of the Northwind expense portal as a confidential web app using the Microsoft Authentication Library (MSAL) for Python. The goal: sign the user in and call Graph to read their upcoming events.

First, register the app and capture its identity with the `az` CLI:

```bash
# Register the confidential web app in Entra ID
az ad app create \
  --display-name "Northwind Expense Portal" \
  --web-redirect-uris "https://localhost:5000/auth/callback" \
  --sign-in-audience AzureADMyOrg

# Note the appId returned, then add a client secret
az ad app credential reset --id <appId> --append
```

Store the resulting `appId` (client ID), tenant ID, and secret as environment variables — never in source. Now acquire a token using the authorization code flow with MSAL:

```python
import os
import msal
import requests

TENANT_ID = os.environ["NW_TENANT_ID"]
CLIENT_ID = os.environ["NW_CLIENT_ID"]
CLIENT_SECRET = os.environ["NW_CLIENT_SECRET"]
REDIRECT_URI = "https://localhost:5000/auth/callback"
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES = ["Calendars.Read"]  # delegated: act as the signed-in user

app = msal.ConfidentialClientApplication(
    CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET
)

# Step 1: send the user here to sign in
auth_url = app.get_authorization_request_url(SCOPES, redirect_uri=REDIRECT_URI)
print("Redirect the browser to:", auth_url)

# Step 2: in your /auth/callback handler, exchange the returned code for tokens
def handle_callback(auth_code: str) -> str:
    result = app.acquire_token_by_authorization_code(
        auth_code, scopes=SCOPES, redirect_uri=REDIRECT_URI
    )
    if "access_token" not in result:
        raise RuntimeError(result.get("error_description", "token acquisition failed"))
    return result["access_token"]

# Step 3: call Microsoft Graph as the user
def get_upcoming_events(access_token: str) -> list[dict]:
    resp = requests.get(
        "https://graph.microsoft.com/v1.0/me/events?$top=5&$select=subject,start",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["value"]
```

The flow is now explicit: `get_authorization_request_url` sends the employee to Entra ID's sign-in page; after they authenticate and consent to `Calendars.Read`, Entra ID redirects back with a code; `acquire_token_by_authorization_code` trades that code (with your secret) for an access token; and the Graph call uses `/me/events`, which resolves to *the signed-in user's* calendar precisely because the token is delegated. Observe that nowhere did your code see the user's password.

## Common pitfalls

- **Confusing delegated and application permissions.** Granting `Calendars.Read` as an application permission lets your daemon read *everyone's* calendar tenant-wide — a massive over-grant for a per-user portal. Use delegated permissions whenever a user is signed in.
- **Putting the client secret in source or front-end code.** A secret in a single-page app's JavaScript is public to anyone with dev tools. SPAs must use the authorization code flow with PKCE and *no* secret; only confidential server apps hold secrets, and those belong in Key Vault (module two).
- **Requesting tokens for the wrong audience.** A token's `aud` claim binds it to one resource. Acquiring a token for your own API and sending it to Graph yields `401`. Request scopes for the resource you are actually going to call.
- **Ignoring token lifetime and caching.** Access tokens expire (commonly around an hour — verify in the docs). Re-running the full interactive flow on every request is wrong and slow; use MSAL's token cache and refresh tokens to renew silently.
- **Hard-coding the `common` authority for a single-tenant line-of-business app.** Using `/common` allows any Microsoft account to attempt sign-in. For an internal portal, target your specific `TENANT_ID` so only Northwind identities are accepted.

## Knowledge check

1. Your daemon service runs nightly with no user present and must read all employees' mailboxes. Which permission type and OAuth flow do you use, and why?
2. A teammate's single-page React app stores a client secret to call Graph. What is wrong, and what should they do instead?
3. The portal acquires a token for its own backend API but receives `401` when calling Microsoft Graph with it. What is the likely cause?

<details>
<summary>Answers</summary>

1. **Application permissions with the client credentials flow** — there is no signed-in user, so the app must act as itself, and application permissions plus client credentials are designed for unattended daemons (with admin consent). Rationale: delegated permissions require a user context that does not exist here.
2. **A SPA cannot keep a secret** — anyone can read it in the browser. They should use the authorization code flow with PKCE and no client secret. Rationale: public clients prove themselves with PKCE, not credentials, because front-end code is inherently exposed.
3. **The token's audience is the backend API, not Graph** — tokens are bound to a single resource by the `aud` claim. They must request a Graph-scoped token (e.g. `Calendars.Read`) for Graph calls. Rationale: a resource rejects tokens minted for a different audience.

</details>

## Summary

The Microsoft identity platform replaces passwords with signed, audience-scoped tokens issued through OpenID Connect and OAuth 2.0. You register your app to give it an identity, choose a flow based on whether a human is signing in, prefer delegated permissions for least privilege, and call Microsoft Graph with an access token whose scopes match the registration. With identity solved, the next problem is the secret your confidential app needs to authenticate — which is exactly what *Secrets, keys, and managed identities* removes from your code entirely.

## Further learning

- [Microsoft identity platform overview](https://learn.microsoft.com/en-us/entra/identity-platform/v2-overview)
- [OAuth 2.0 authorization code flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow)
- [Permissions and consent in the Microsoft identity platform](https://learn.microsoft.com/en-us/entra/identity-platform/permissions-consent-overview)
- [Use MSAL Python to acquire tokens](https://learn.microsoft.com/en-us/entra/msal/python/)
