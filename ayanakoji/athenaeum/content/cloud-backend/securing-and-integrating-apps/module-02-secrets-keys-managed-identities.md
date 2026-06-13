---
kind: module
id: cb-c03-m02
vertical: cloud-backend
course_id: cb-c03
title: Secrets, keys, and managed identities
level: advanced
grounded_on: "AZ-204 skills outline (2026-01-14), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-204
synthetic: true
order: 2
prereqs: [cb-c03-m01]
objectives:
  - Store and retrieve secrets, keys, and certificates from Azure Key Vault
  - Use managed identities to access Azure resources without credentials in code
  - Secure application configuration data and reason about shared access signatures
---

# Secrets, keys, and managed identities

In the previous module the Northwind Logistics expense portal held a client secret so it could exchange an authorization code for tokens. That secret had to live *somewhere*. If you put it in `appsettings.json`, it leaks the moment the repo is cloned. If you put it in an environment variable on the host, it shows up in process listings and crash dumps. And it expires, so someone has to remember to rotate it before the portal stops signing people in at 2 a.m. The deeper problem is that a credential your code can read is a credential an attacker can read too. This module shows you how to store secrets in **Azure Key Vault** and — better still — how to remove most stored credentials entirely with **managed identities**, so your code authenticates with *who it is* rather than *what it knows*.

## Learning objectives

By the end of this module you will be able to:

- Create an Azure Key Vault and store secrets, keys, and certificates in it.
- Retrieve secrets at runtime using the Azure SDK and `DefaultAzureCredential`.
- Assign a managed identity to an Azure service and grant it least-privilege access via RBAC.
- Decide when a shared access signature (SAS) is the right tool and scope it safely.

## Concepts

### Key Vault: a hardened store for the things you must protect

Azure Key Vault is a managed service for three kinds of material: **secrets** (arbitrary strings like connection strings and API keys), **keys** (cryptographic keys for signing or encryption, which can be backed by an HSM and used without ever leaving the vault), and **certificates** (TLS certs with managed lifecycle). The point is centralization and control: secrets live in one audited place, access is governed by policy, every read is logged, and you can rotate a value in one location instead of hunting through deployment manifests.

Access to a vault has two layers. The **management plane** controls the vault resource itself (who can create or delete it) and is governed by Azure RBAC. The **data plane** controls who can read or write the secrets inside, governed either by the older **access policies** model or, preferably, by **Azure RBAC** with roles like *Key Vault Secrets User*. RBAC is recommended because it is consistent with the rest of Azure and supports fine-grained, auditable assignments. A frequent confusion is granting management-plane access (e.g. *Contributor*) and expecting to read secrets — you also need a data-plane role.

### Managed identities: the credential you never see

A managed identity is an identity for an Azure resource — a Function app, a web app, a VM — that Entra ID manages for you. There is **no secret to store, rotate, or leak**; the platform issues short-lived tokens to the resource automatically. There are two flavors. A **system-assigned** identity is tied one-to-one to a single resource and is deleted with it. A **user-assigned** identity is a standalone resource you create once and attach to many services — useful when several apps need the same access, or when you want the identity to outlive any single app.

The mechanism is elegant. When your code runs on a resource with a managed identity, the Azure SDK's `DefaultAzureCredential` discovers it through the host environment and obtains a token from Entra ID with no credential in sight. The same `DefaultAzureCredential` falls back to your `az login` session during local development, so identical code works on your laptop and in production. This is why the modern guidance is: *grant the app's managed identity a role on Key Vault, and stop storing the vault's own credentials altogether.*

### Shared access signatures: delegated, time-boxed access to storage

Sometimes you must hand a *third party* temporary access to a specific resource without sharing an account key. A **shared access signature (SAS)** is a signed URL that grants narrowly scoped, time-limited permissions to Azure Storage — for example, "read this one blob for the next 15 minutes." Prefer a **user delegation SAS**, which is signed with Entra ID credentials rather than the storage account key, because it can be tied to a managed identity and revoked by rotating the user delegation key. Always scope a SAS to the least permission, the shortest lifetime, and the narrowest resource that the scenario allows; a long-lived, account-key-signed, read-write SAS on a whole container is a liability.

## Walkthrough: giving the portal a managed identity to read its secret

You will refactor the Northwind expense portal so its Azure Functions backend reads the Entra client secret from Key Vault using a system-assigned managed identity — eliminating the secret from configuration. First, provision the vault and store the secret:

```bash
# Create the vault with RBAC authorization for the data plane
az keyvault create \
  --name nw-expense-kv \
  --resource-group rg-northwind-expense \
  --location eastus \
  --enable-rbac-authorization true

# Store the Entra client secret as a Key Vault secret
az keyvault secret set \
  --vault-name nw-expense-kv \
  --name "EntraClientSecret" \
  --value "<the-secret-value>"
```

Next, turn on the Function app's system-assigned identity and grant it read access to secrets:

```bash
# Enable the system-assigned managed identity and capture its principal ID
PRINCIPAL_ID=$(az functionapp identity assign \
  --name nw-expense-func \
  --resource-group rg-northwind-expense \
  --query principalId -o tsv)

# Get the vault's resource ID for the role scope
KV_ID=$(az keyvault show --name nw-expense-kv --query id -o tsv)

# Grant least-privilege data-plane access: read secrets only
az role assignment create \
  --assignee "$PRINCIPAL_ID" \
  --role "Key Vault Secrets User" \
  --scope "$KV_ID"
```

Now the application code reads the secret with no stored credential whatsoever:

```python
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

VAULT_URL = "https://nw-expense-kv.vault.azure.net"

# DefaultAzureCredential finds the managed identity in Azure,
# or your `az login` session when running locally.
credential = DefaultAzureCredential()
client = SecretClient(vault_url=VAULT_URL, credential=credential)

def get_entra_client_secret() -> str:
    secret = client.get_secret("EntraClientSecret")
    return secret.value
```

What changed: there is no client secret in `appsettings.json`, no secret in an environment variable, and nothing to rotate in your deployment. The Function authenticates to Key Vault *as itself* using a platform-issued token, the `Key Vault Secrets User` role lets it read but not write or delete, and the same code runs locally because `DefaultAzureCredential` falls back to your signed-in CLI session.

## Common pitfalls

- **Granting management-plane access but not data-plane.** A *Contributor* role on the vault does not let you read secrets. With RBAC authorization enabled you must also assign a data-plane role such as *Key Vault Secrets User*. Mismatched planes produce confusing `403`s.
- **Caching `DefaultAzureCredential` per call but recreating clients constantly.** Construct the `SecretClient` once and reuse it; recreating it on every request adds latency and token traffic. Conversely, do not cache the secret *value* forever — if you rotate it, your app must pick up the new one.
- **Leaving access policies and RBAC half-migrated.** A vault uses *either* access policies or RBAC for the data plane. Enabling RBAC while expecting old access policies to still apply leads to silent denials. Pick one model deliberately.
- **Issuing broad, long-lived SAS tokens.** An account-key-signed SAS that grants read-write on a whole container for a year cannot be easily revoked and is dangerous if leaked. Use a user-delegation SAS, least permission, and short expiry.
- **Forgetting the local-dev story.** Code that only works with a managed identity fails on a laptop. `DefaultAzureCredential` solves this, but the developer must be signed in with `az login` and have the same RBAC role, or local runs will `403`.

## Knowledge check

1. Your Function app has the *Contributor* role on its Key Vault but `get_secret` still returns `403`. What is missing?
2. Two separate apps both need read access to the same vault, and you want the identity to survive even if one app is deleted. System-assigned or user-assigned identity — and why?
3. A partner needs to download one report blob for the next ten minutes. What mechanism do you use, and what two properties must you constrain?

<details>
<summary>Answers</summary>

1. **A data-plane role assignment** such as *Key Vault Secrets User*. Rationale: *Contributor* is a management-plane role; with RBAC authorization the data plane requires its own role to read secret values.
2. **A user-assigned managed identity.** Rationale: it is a standalone resource that can be attached to multiple apps and persists independently of any single app's lifecycle, unlike a system-assigned identity which is deleted with its host.
3. **A shared access signature (preferably a user-delegation SAS)**, constrained to **least permission (read-only)** and **shortest lifetime (ten minutes)**, scoped to that single blob. Rationale: narrow scope and short expiry limit the blast radius if the URL leaks.

</details>

## Summary

Key Vault centralizes secrets, keys, and certificates behind audited, policy-governed access, and managed identities go one step further by removing the stored credential altogether — your code authenticates as the resource itself via `DefaultAzureCredential`. Match management-plane and data-plane roles deliberately, prefer least-privilege RBAC, and reserve short-lived, narrowly scoped SAS tokens for delegating storage access to third parties. With identity established and secrets secured, you are ready to expose your services to the outside world safely, which is the focus of *Publishing APIs with Azure API Management*.

## Further learning

- [About Azure Key Vault](https://learn.microsoft.com/en-us/azure/key-vault/general/overview)
- [What are managed identities for Azure resources?](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/overview)
- [DefaultAzureCredential and the Azure Identity client library](https://learn.microsoft.com/en-us/azure/developer/python/sdk/authentication/credential-chains)
- [Grant permission to applications to access a key vault using Azure RBAC](https://learn.microsoft.com/en-us/azure/key-vault/general/rbac-guide)
