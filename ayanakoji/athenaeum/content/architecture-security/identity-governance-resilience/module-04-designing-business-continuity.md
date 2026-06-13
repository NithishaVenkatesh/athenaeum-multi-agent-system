---
kind: module
id: as-c02-m04
vertical: architecture-security
course_id: as-c02
title: Designing business continuity
level: intermediate
grounded_on: "AZ-305 skills outline (2026-04-17), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-305
synthetic: true
order: 4
prereqs: [as-c02-m03]
objectives:
  - Recommend backup and disaster-recovery solutions for Azure and hybrid workloads that meet RTO and RPO
  - Design high-availability solutions for compute using availability zones and regional redundancy
  - Recommend a high-availability and recovery solution for relational data
---

# Designing business continuity

Aurora Health, a fictional telemedicine provider, has a polished, well-monitored platform — until a regional service disruption takes its primary Azure region offline for six hours. Patients cannot book appointments, clinicians cannot reach records, and the leadership team discovers that "we have backups" and "we can recover the business in an hour" are very different statements. Backups existed but had never been restore-tested; the database had no secondary region; nobody had written down how long recovery would actually take. Business continuity is the pillar that is invisible until the day it is the only thing that matters. This module teaches you to design backup, disaster recovery, and high availability against explicit, numeric objectives — so that "we can recover" is a measured fact, not a hope.

## Learning objectives

By the end of this module you will be able to:

- Recommend backup and disaster-recovery solutions for Azure and hybrid workloads that meet stated recovery objectives.
- Express and design to recovery-time objective (RTO) and recovery-point objective (RPO).
- Design high-availability solutions for compute using availability zones and multi-region patterns.
- Recommend a high-availability and recovery solution for relational data.

## Concepts

### The two numbers that drive every decision: RTO and RPO

Before choosing any technology, you anchor on two numbers, because they determine everything else and they are what the business actually cares about. **Recovery-time objective (RTO)** is how long the workload may be unavailable after a failure — the maximum tolerable downtime. **Recovery-point objective (RPO)** is how much data you can afford to lose, measured as a time window — if your RPO is five minutes, a recovery may discard at most the last five minutes of writes.

These are *business* decisions disguised as technical ones. Aurora Health's appointment booking might tolerate an RTO of an hour but an RPO of near-zero (losing booking data is unacceptable), while an internal analytics dashboard might tolerate an RTO of a day and an RPO of 24 hours. Tighter objectives cost more — near-zero RPO implies synchronous replication and its latency and expense. The architect's job is to match the design to the *stated* objectives, not to gold-plate everything to zero, and to make the cost of each tier visible so the business chooses with open eyes.

### High availability vs. disaster recovery: different failures

These two terms get conflated, and the distinction shapes the design. **High availability** keeps a workload running through *localized* failures — a failed disk, a rebooting host, a single data-center fault — usually within one region and ideally with no data loss and near-zero RTO. **Disaster recovery** is the plan for a *regional* loss: failing the workload over to an entirely different region. HA is about redundancy you never think about; DR is about a deliberate, tested failover you hope never to invoke.

Azure regions are built from **availability zones** — physically separate data centers within a region, each with independent power, cooling, and networking. Deploying across zones protects against a data-center-level fault while staying in-region (so latency stays low and no cross-region data-residency questions arise). That covers HA. For DR you need a *second region*, typically a paired or otherwise distant region, with data replicated there and a way to redirect traffic. Designing only zonal redundancy and calling it disaster recovery is a classic gap — a regional outage like Aurora's takes down every zone at once.

### Backup, replication, and the tools

Three mechanisms, three purposes. **Backup** (Azure Backup, via a Recovery Services vault) produces point-in-time copies for restoring from corruption, accidental deletion, or ransomware — its RPO is the backup frequency and its RTO is the restore time. **Replication** continuously copies data to a secondary, giving a much tighter RPO; **Azure Site Recovery** orchestrates replication and failover of whole VMs (Azure-to-Azure or on-premises-to-Azure) for hybrid DR. For data services, replication is often built in — see relational data below.

Crucially, a backup you have never restored is a guess, not a recovery plan. Aurora's central failure was never testing a restore. Design a periodic restore drill and a documented, rehearsed failover runbook; an untested DR plan reliably fails on the day you need it.

### High availability for relational data

Relational databases are usually the hardest part, because they hold the state everything else depends on. Azure SQL Database and Azure Database for PostgreSQL/MySQL offer **zone-redundant** configurations that place replicas across availability zones for in-region HA with automatic failover. For cross-region DR, features such as **active geo-replication** or **failover groups** maintain a continuously updated readable secondary in another region; a failover group also gives you a stable connection endpoint that redirects to whichever region is primary, so the application does not have to change its connection string during a failover. The replication is asynchronous across regions, so the cross-region RPO is small but not zero — verify the current behavior and any zero-data-loss options in the docs, as these capabilities and their guarantees evolve.

## Walkthrough: a continuity design for Aurora's booking service

Aurora's leadership states the objectives for the appointment-booking workload: RTO of one hour, RPO of five minutes. You design HA with availability zones in the primary region and DR with a SQL failover group to a secondary region. Here is the relational-data piece expressed in Bicep — a zone-redundant primary database plus a failover group binding it to a secondary server:

```bicep
param primaryServerName string = 'sql-aurora-booking-primary'
param databaseName string = 'booking'
param secondaryServerId string  // resourceId of the pre-provisioned secondary SQL server

// Zone-redundant database for in-region high availability.
resource db 'Microsoft.Sql/servers/databases@2023-08-01-preview' = {
  name: '${primaryServerName}/${databaseName}'
  location: resourceGroup().location
  sku: { name: 'BC_Gen5', tier: 'BusinessCritical', capacity: 4 }
  properties: {
    zoneRedundant: true            // replicas spread across availability zones
  }
}

// Failover group for cross-region disaster recovery.
resource fog 'Microsoft.Sql/servers/failoverGroups@2023-08-01-preview' = {
  name: '${primaryServerName}/fog-aurora-booking'
  properties: {
    partnerServers: [ { id: secondaryServerId } ]
    databases: [ db.id ]
    readWriteEndpoint: {
      failoverPolicy: 'Automatic'  // auto-failover on a sustained regional outage
      failoverWithDataLossGracePeriodMinutes: 60
    }
  }
}
```

Two layers of protection are encoded here. `zoneRedundant: true` on a Business Critical database spreads replicas across availability zones, so a single data-center fault fails over automatically within the region with no data loss — that is the HA layer, and it is what Aurora was missing for routine faults. The `failoverGroup` adds the DR layer: it keeps a continuously replicated secondary in another region and exposes a read-write listener endpoint, so when the failover policy triggers, the application's connection — pointed at the failover-group endpoint, not a server name — follows the primary to the new region without a config change. The `failoverWithDataLossGracePeriodMinutes` of 60 ties directly to the one-hour RTO: Azure waits up to that grace period attempting a clean failover before forcing one. You would pair this with availability-zone-spread compute and a tested failover runbook, then *rehearse* it — because the only way to know your RTO is real is to measure a drill.

## Common pitfalls

- **Confusing zonal HA with disaster recovery.** Spreading across availability zones protects against a data-center fault but not a regional outage, which takes every zone down together. If the requirement is regional resilience, you need a second region.
- **Never testing restores or failovers.** This was Aurora's actual failure. A backup or DR design that has never been exercised is an assumption; schedule restore drills and rehearse the failover runbook so RTO and RPO are measured, not hoped.
- **Designing to zero RPO everywhere.** Synchronous, zero-loss replication is expensive and adds latency. Match the objective to each workload's real tolerance instead of gold-plating, and let the business see the cost of each tier.
- **Hard-coding a regional endpoint in the app.** If the application connects to a specific server name rather than a failover-group listener, a failover requires a manual config change under pressure. Use the abstracted endpoint so failover is transparent.
- **Treating backup as disaster recovery.** Backups protect against corruption and deletion but typically have a longer RTO than replication-based failover. For a tight regional-outage RTO, you need replication, not just backup — they solve different problems.

## Knowledge check

1. Aurora's booking workload has an RPO of five minutes and must survive the loss of an entire region. Why is an availability-zone-only design insufficient, and what do you add?
2. The application currently connects to `sql-aurora-booking-primary.database.windows.net`. Why is this a problem for disaster recovery, and what do you change?
3. Leadership asks why the analytics workload, which only needs daily reporting, shouldn't get the same near-zero RPO design as booking. How do you justify a cheaper design?

<details>
<summary>Answers</summary>

1. Availability zones protect only against an in-region data-center fault; a regional outage takes all zones down simultaneously. You add a cross-region disaster-recovery layer — for example a SQL failover group replicating to a secondary region.
2. Connecting to the specific primary server name means a regional failover requires a manual connection-string change under pressure. Point the app at the failover-group read-write listener endpoint so the connection follows the primary to the new region automatically.
3. RTO and RPO are business-driven and tighter objectives cost more (synchronous replication, secondary infrastructure). An analytics workload tolerating a day of RTO and 24-hour RPO is well served by periodic backup, so spending on near-zero RPO there is unjustified gold-plating.

</details>

## Summary

Business continuity is designed against two numbers — RTO and RPO — that the business owns, and the architect's job is to match technology to those objectives rather than over-engineering everything to zero. Separate high availability (availability zones, in-region, for localized faults) from disaster recovery (a second region with replication, for regional loss), use backup for corruption and deletion, and above all *test* every restore and failover, because an unrehearsed plan fails when it counts. This module closes the course: with identity, governance, observability, and resilience designed deliberately, you are equipped to architect Azure platforms — and ready for the Zero-Trust depth of **Zero-Trust Security Architecture** (as-c03).

## Further learning

- [Azure Backup overview](https://learn.microsoft.com/en-us/azure/backup/backup-overview)
- [About Site Recovery](https://learn.microsoft.com/en-us/azure/site-recovery/site-recovery-overview)
- [What are Azure availability zones?](https://learn.microsoft.com/en-us/azure/reliability/availability-zones-overview)
- [Failover groups overview & best practices (Azure SQL Database)](https://learn.microsoft.com/en-us/azure/azure-sql/database/failover-group-sql-db)
