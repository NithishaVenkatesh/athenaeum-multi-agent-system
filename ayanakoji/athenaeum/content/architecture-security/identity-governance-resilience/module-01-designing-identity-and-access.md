---
kind: module
id: as-c02-m01
vertical: architecture-security
course_id: as-c02
title: Designing identity and access
level: intermediate
grounded_on: "AZ-305 skills outline (2026-04-17), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-305
synthetic: true
order: 1
prereqs: [as-c01]
objectives:
  - Recommend an authentication and identity-management solution for cloud and hybrid users
  - Design an authorization model using Azure RBAC, custom roles, and Privileged Identity Management
  - Recommend a solution to manage secrets, certificates, and keys with Azure Key Vault
---

# Designing identity and access

Meridian Outfitters, a fictional outdoor-gear retailer, is merging with a logistics company it just acquired. Suddenly there are two directories, two sets of employees, a warehouse-floor application that still uses a shared service account, and a contractor population that needs read access to exactly one resource group for exactly three months. The CISO wants single sign-on for everyone, no standing administrative access, and a clean audit trail. The infrastructure already exists — the question on the table is identity, and a wrong answer here is the kind that ends up in a breach post-mortem. This module teaches you to design that identity and access layer as a deliberate system rather than a pile of accidental grants.

## Learning objectives

By the end of this module you will be able to:

- Recommend an authentication and identity-management solution that fits cloud-only, hybrid, and external-user requirements.
- Design an authorization model using Azure role-based access control, custom roles, and Privileged Identity Management.
- Recommend a solution to manage secrets, certificates, and keys using Azure Key Vault and managed identities.
- Distinguish the control plane from the data plane when reasoning about who can do what.

## Concepts

### Authentication: identity as the new perimeter

In a Zero-Trust model, the network is no longer the boundary; identity is. So the first design decision is *which identities exist and where they are mastered*. Microsoft Entra ID is the cloud identity provider, but most enterprises also run Active Directory on-premises, which means you are designing a synchronization story, not a greenfield directory.

For hybrid users, Microsoft Entra Connect synchronizes on-premises identities into the cloud directory. The consequential choice is the authentication method. *Password hash synchronization* copies a hash-of-a-hash of each password into the cloud, so authentication happens entirely in Entra ID even if the on-premises domain controllers are down — the most resilient option. *Pass-through authentication* validates the password against on-premises Active Directory in real time, which some organizations require for policy reasons but which couples cloud sign-in to on-premises availability. *Federation* with AD FS hands authentication to an on-premises identity provider entirely; it is the most complex to operate and is rarely the right default anymore. As a rule of thumb, recommend password hash synchronization unless a concrete requirement forbids it.

Layered on top is *Conditional Access*: policies that evaluate signals — user, device, location, risk — and decide to allow, block, or require multi-factor authentication. Conditional Access is where "require MFA for administrators" and "block legacy authentication protocols" actually get enforced. For external users such as Meridian's contractors, Microsoft Entra External ID (the business-to-business collaboration model) lets you invite guests who authenticate with their own home identity, so you never manage their passwords.

### Authorization: RBAC, custom roles, and least privilege

Authentication proves *who you are*; authorization decides *what you may do*. Azure role-based access control grants permissions by assigning a **role** to a **security principal** (user, group, service principal, or managed identity) at a **scope** (management group, subscription, resource group, or individual resource). Assignments are inherited downward, so a Reader role granted at a subscription applies to every resource group beneath it.

Prefer built-in roles, and prefer assigning them to groups rather than individuals so that access follows group membership. Reach for a *custom role* only when no built-in role expresses the intent — for example, "may restart virtual machines but may not delete them." A critical distinction: the **control plane** (managing the resource through Azure Resource Manager — `Microsoft.Storage/storageAccounts/write`) is governed by RBAC, while the **data plane** (reading the actual blobs inside that storage account) may be governed by a separate role or by the resource's own access model. Granting Owner on a subscription does not automatically grant data-plane access to encrypted data, and conflating the two is a common design error.

For privileged roles, standing access is the enemy. **Privileged Identity Management (PIM)** makes roles *eligible* rather than *active*: an administrator activates the role just-in-time, for a bounded window, optionally with approval and justification, and every activation is logged. This is how you deliver the CISO's "no standing administrative access" requirement without making admins unable to do their jobs.

### Secrets, keys, and certificates

Credentials in code are the original sin of cloud security. The design goal is that no application ever stores a password, connection string, or certificate in source or configuration. **Azure Key Vault** is the centralized store for secrets, keys, and certificates, with its own access model (Azure RBAC data-plane roles such as Key Vault Secrets User, or the older vault access policies). For keys that must never leave hardware, Key Vault offers an HSM-backed tier — verify the current tier names and FIPS levels in the docs, as these evolve.

The piece that makes it credential-free is the **managed identity**. Azure issues an identity to a resource (a VM, a function, a container app), and that identity can be granted access to Key Vault and other services. The application then authenticates *as itself* with no secret to leak. A *system-assigned* identity is tied to the lifecycle of one resource; a *user-assigned* identity is a standalone object you can share across many resources — useful when several services need the same access.

## Walkthrough: locking down Meridian's warehouse app

Meridian's warehouse application reads a database connection string and a third-party shipping-API key. Today both sit in an app setting in plain text. You will redesign it so the app holds no secrets, retrieves them from Key Vault using a managed identity, and gives the operations team just-in-time access to manage the vault.

The control-plane design, expressed as a Bicep module, provisions the vault with RBAC authorization enabled and grants the app's user-assigned managed identity the data-plane role to read secrets:

```bicep
@description('Region and naming for the Meridian warehouse vault.')
param location string = resourceGroup().location
param vaultName string = 'kv-meridian-warehouse'
param appIdentityPrincipalId string // objectId of the user-assigned managed identity

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: vaultName
  location: location
  properties: {
    tenantId: subscription().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true      // use Azure RBAC, not legacy access policies
    enableSoftDelete: true
    enablePurgeProtection: true        // block permanent deletion during retention
  }
}

// Built-in role: Key Vault Secrets User (read secret values at the data plane).
var secretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'

resource secretsRead 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vault.id, appIdentityPrincipalId, secretsUserRoleId)
  scope: vault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', secretsUserRoleId)
    principalId: appIdentityPrincipalId
    principalType: 'ServicePrincipal'  // managed identities are service principals
  }
}
```

Two design choices are doing the work here. First, `enableRbacAuthorization: true` means vault access is governed by the same RBAC model as everything else, so access reviews and PIM apply uniformly rather than living in a separate access-policy island. Second, the role is scoped to the *vault*, not the subscription — least privilege. The application code then uses `DefaultAzureCredential` to acquire a token for its managed identity and read the secret; there is no secret in the app at all. Separately, you would configure PIM so that the "Key Vault Administrator" role is eligible (not active) for the operations team, with approval required — satisfying "no standing admin access."

## Common pitfalls

- **Granting Owner when Contributor or a custom role would do.** Owner includes the right to grant access to others, which quietly turns one over-privileged account into a lateral-movement risk. Start from the least-powerful role that meets the need.
- **Confusing control-plane and data-plane access.** A principal with Contributor on a storage account can change its configuration but may still be unable to read blobs if data-plane RBAC is enforced. Design both planes explicitly and state which you mean.
- **Leaving legacy authentication enabled.** Protocols that cannot do MFA are a favorite for password-spray attacks. A Conditional Access policy blocking legacy auth is one of the highest-value, lowest-effort controls — but verify current protocol coverage in the docs before assuming it is complete.
- **Standing global administrators.** Permanent high-privilege role assignments defeat the purpose of just-in-time access. Use PIM eligibility with time bounds and approval for anything privileged.
- **Storing secrets "temporarily" in app settings.** Temporary becomes permanent. Design managed-identity access to Key Vault from the start, because retrofitting it after a leak is far more painful.

## Knowledge check

1. Meridian needs cloud sign-in to keep working even if its on-premises domain controllers go offline during a data-center outage. Which Entra Connect authentication method best meets this, and why?
2. An application running on Azure Container Apps must read a connection string from Key Vault, and the security team forbids any secret in configuration. What two design elements combine to achieve this?
3. The operations team needs to manage the Key Vault occasionally but the CISO forbids standing administrative access. What do you recommend, and what does it give you beyond just-in-time access?

<details>
<summary>Answers</summary>

1. Password hash synchronization — authentication happens entirely in Entra ID using synchronized hashes, so it does not depend on on-premises availability, unlike pass-through authentication or federation.
2. A managed identity assigned to the container app, plus an RBAC data-plane role (such as Key Vault Secrets User) scoped to the vault granting that identity read access — the app authenticates as itself with no stored secret.
3. Privileged Identity Management with the administrative role configured as eligible rather than active — beyond just-in-time activation it gives you approval workflows, time-bounded sessions, and a complete audit trail of every activation.

</details>

## Summary

Identity is the real perimeter, so design it as a system: choose an authentication and synchronization model that matches your hybrid and availability requirements, enforce least privilege with RBAC and custom roles only where built-in roles fall short, eliminate standing privilege with PIM, and remove credentials from code entirely using Key Vault and managed identities. Keep the control plane and data plane distinct in your reasoning. With identity designed, the next module zooms out to **Designing governance** — how to keep hundreds of subscriptions and the access within them consistent and compliant at scale.

## Further learning

- [What is Azure role-based access control (Azure RBAC)?](https://learn.microsoft.com/en-us/azure/role-based-access-control/overview)
- [What is Privileged Identity Management?](https://learn.microsoft.com/en-us/entra/id-governance/privileged-identity-management/pim-configure)
- [What are managed identities for Azure resources?](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/overview)
- [Azure Key Vault basic concepts](https://learn.microsoft.com/en-us/azure/key-vault/general/basic-concepts)
