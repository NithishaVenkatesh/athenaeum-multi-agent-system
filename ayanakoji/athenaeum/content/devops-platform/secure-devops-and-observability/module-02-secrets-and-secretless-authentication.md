---
kind: module
id: do-c03-m02
vertical: devops-platform
course_id: do-c03
title: Secrets and secretless authentication
level: advanced
grounded_on: "AZ-400 skills outline (2026-04-24), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-400
synthetic: true
order: 2
prereqs: [do-c03-m01]
objectives:
  - Store and retrieve secrets, keys, and certificates centrally with Azure Key Vault
  - Implement secretless authentication using workload identity federation with OIDC
  - Design pipelines that structurally prevent leakage of sensitive information
---

# Secrets and secretless authentication

Meridian Freight's incident review found the cause in ninety seconds: a service-principal secret, pasted into a pipeline variable years ago, had been printed to a build log when someone added `set -x` for debugging. The log was retained, the secret never expired, and it granted contributor rights to the whole subscription. Rotating it broke four pipelines nobody remembered owning. Every part of this is avoidable. The mature answer is not "store the secret more carefully" — it is "have no secret to store." This module takes you from centralizing secrets in Key Vault to eliminating long-lived credentials altogether with workload identity federation.

## Learning objectives

By the end of this module you will be able to:

- Store and retrieve secrets, keys, and certificates centrally using Azure Key Vault with RBAC access control.
- Use managed identities so application code never holds a credential.
- Implement secretless authentication for pipelines using workload identity federation (OIDC) in GitHub Actions and Azure Pipelines.
- Design pipelines that structurally prevent secret leakage into logs and artifacts.

## Concepts

### Centralizing trust in Key Vault

Azure Key Vault is a dedicated store for three kinds of material: *secrets* (arbitrary strings like connection strings), *keys* (cryptographic keys for signing or wrapping), and *certificates*. The point of a vault is not merely encryption at rest — it is *centralized control*: one place to set access policy, one audit trail of who read what, and one place to rotate. When a credential lives in a vault rather than scattered across pipeline variables and config files, rotation becomes a single operation instead of an archaeology project.

Access to a vault can be governed by access policies or, preferably, by Azure RBAC roles such as *Key Vault Secrets User*. RBAC integrates with the same identity model as the rest of Azure, so you grant a specific identity read access to secrets and nothing more. The principle is least privilege: the booking API's identity can read its own connection string and cannot enumerate the vault.

### Managed identities: credentials you never see

A *managed identity* is an identity in Microsoft Entra ID that Azure manages for you and attaches to a resource — an app, a function, a VM. The resource can request a token for that identity from the platform without ever holding a client secret. There are two flavors: *system-assigned* (tied to one resource's lifecycle) and *user-assigned* (a standalone identity you can attach to several resources).

In code you do not handle any of this directly. The Azure SDKs ship `DefaultAzureCredential`, a credential that tries a chain of sources — environment variables, managed identity, developer sign-in — and uses whichever is available. The same code authenticates as a managed identity in Azure and as the developer locally, with no secret in either case. This is the cleanest pattern for *runtime* access: the app reads its Key Vault secret using its managed identity, and there is nothing to leak.

### Workload identity federation for pipelines

Managed identities solve the running app, but a *pipeline* runs on GitHub or Azure DevOps, outside your Azure resources — so what does it authenticate as? The old answer was a service principal with a client secret stored in the pipeline. The modern answer is *workload identity federation*, built on OpenID Connect (OIDC).

The mechanism: you register a *federated credential* on an Entra app registration or user-assigned managed identity that trusts tokens issued by the pipeline platform's OIDC provider, scoped to a specific repository, branch, or environment. At run time the pipeline requests a short-lived OIDC token from its own platform asserting "I am the deploy job for the main branch of meridian/booking-api." It presents that token to Entra, which checks it against the federated credential's subject claim and, if it matches, issues a normal Azure access token. No secret is ever stored, transmitted, or rotated — the trust is in the *claim*, and the token expires in minutes.

## Walkthrough: a secretless deploy for the booking API

Meridian wants the booking API's deploy pipeline to authenticate to Azure with zero stored secrets, and the running API to read its database connection string from Key Vault using a managed identity. First, configure the federated trust for the pipeline using the CLI:

```bash
# 1. Create a user-assigned identity the pipeline will federate to
az identity create \
  --name id-meridian-deploy \
  --resource-group rg-meridian-shared

# Capture its details for the federation and role assignment
APP_OBJECT_ID=$(az identity show -n id-meridian-deploy -g rg-meridian-shared --query principalId -o tsv)
CLIENT_ID=$(az identity show -n id-meridian-deploy -g rg-meridian-shared --query clientId -o tsv)

# 2. Trust GitHub OIDC tokens from the main branch of the repo only
az identity federated-credential create \
  --name github-main \
  --identity-name id-meridian-deploy \
  --resource-group rg-meridian-shared \
  --issuer "https://token.actions.githubusercontent.com" \
  --subject "repo:meridian-freight/booking-api:ref:refs/heads/main" \
  --audiences "api://AzureADTokenExchange"
```

The `subject` is the gate: only a workflow running on `main` in that exact repository can exchange its token. Now the GitHub Actions workflow logs in with no secret — it presents an OIDC token instead:

```yaml
permissions:
  id-token: write   # allows the workflow to request an OIDC token
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Azure login (federated, no secret)
        uses: azure/login@v2
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}      # not a secret — just an id
          tenant-id: ${{ vars.AZURE_TENANT_ID }}
          subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}
      - name: Deploy Bicep
        run: az deployment group create -g rg-meridian-prod -f main.bicep -p prod.bicepparam
```

Notice the client, tenant, and subscription IDs are stored as *variables*, not secrets — they are not sensitive, because they are useless without a token that matches the federated subject. For runtime access, the API code reads its secret with the managed identity and no credential at all:

```python
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

# Resolves to the app's managed identity in Azure; developer sign-in locally
credential = DefaultAzureCredential()
client = SecretClient(
    vault_url="https://kv-meridian-prod.vault.azure.net",
    credential=credential,
)

connection_string = client.get_secret("booking-db-connection").value
```

The result: the deploy authenticates with an expiring OIDC token, the app authenticates with a managed identity, and there is no secret anywhere for a stray `set -x` to print.

## Common pitfalls

- **Echoing secrets in logs.** Enabling shell tracing, printing environment variables for debugging, or interpolating a secret into an error message defeats every other control. Never log secret values; rely on the platform's automatic masking and prefer secretless auth so there is nothing to mask.
- **Over-broad federated subjects.** A federated credential scoped to the whole organization or all branches lets any workflow impersonate your deploy identity. Scope the subject to the exact repository and branch or environment.
- **Keeping the old client secret around.** Adding OIDC but leaving the long-lived service-principal secret in place means you still have the leak surface you set out to remove. Delete the secret once federation works.
- **Granting the identity too much.** A deploy identity with Owner on the subscription is a blast radius, not a convenience. Assign the narrowest role and scope that lets the job do its work.
- **Confusing identifiers with secrets.** Treating client and tenant IDs as secrets adds friction without security; treating an actual client secret as "just config" causes leaks. Know which is which: IDs are public, secrets and certificates are not.

## Knowledge check

1. A pipeline uses workload identity federation. An attacker copies the workflow file, including the `client-id` variable, into their own repository and runs it. Why does the Azure login fail?
2. Why is `DefaultAzureCredential` preferable to reading a connection string for Key Vault from an environment variable in the running app?
3. Your team adds OIDC federation but a security scan still flags a stored credential. What did they most likely forget, and why does it matter?

<details>
<summary>Answers</summary>

1. The OIDC token the attacker's workflow presents carries a `subject` claim for *their* repository, which does not match the federated credential's configured subject (`repo:meridian-freight/booking-api:ref:refs/heads/main`), so Entra refuses to issue an Azure token. — Federation trusts a specific claim, not possession of an ID; the client ID alone is useless.
2. `DefaultAzureCredential` lets the app authenticate as its managed identity with no stored credential at all, eliminating the leak surface; an environment variable holding a credential can still be printed, snapshotted, or exfiltrated. — The goal is to have no secret to protect, not to protect a secret more carefully.
3. They likely left the original service-principal client secret on the app registration. It matters because the leak surface OIDC was meant to remove still exists and remains a valid credential until deleted. — Adding a better path does not retire the worse one; you must remove it.

</details>

## Summary

Secret management on a secure pipeline is a ladder: centralize credentials in Key Vault with least-privilege RBAC, let running code authenticate as a managed identity so it holds nothing, and replace pipeline service-principal secrets with workload identity federation so deploys present short-lived OIDC tokens instead of stored secrets. The unifying idea is to make the credential ephemeral and the trust live in a verifiable claim. With infrastructure declared and credentials secured, the next module ensures the code and dependencies flowing through that pipeline are scanned for vulnerabilities, leaked secrets, and license risk before they ship.

## Further learning

- [About Azure Key Vault](https://learn.microsoft.com/en-us/azure/key-vault/general/overview)
- [What are managed identities for Azure resources?](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/overview)
- [Workload identity federation](https://learn.microsoft.com/en-us/entra/workload-id/workload-identity-federation)
- [Configure a GitHub Actions workflow with OpenID Connect to Azure](https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure-openid-connect)
