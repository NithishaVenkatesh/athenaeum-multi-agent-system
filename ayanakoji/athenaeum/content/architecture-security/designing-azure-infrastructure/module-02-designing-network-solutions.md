---
kind: module
id: as-c01-m02
vertical: architecture-security
course_id: as-c01
title: Designing network solutions
level: foundational
grounded_on: "AZ-305 skills outline (2026-04-17), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-305
synthetic: true
order: 2
prereqs: [as-c01-m01]
objectives:
  - Recommend connectivity solutions to the internet and to on-premises networks
  - Optimize network performance with peering, private connectivity, and acceleration
  - Design a load-balancing and routing solution matched to the traffic type
---

# Designing network solutions

You placed Solstice Tickets' workloads onto compute in the previous module. Now the network team raises three problems no compute choice can solve. The pricing API in `eastus` calls a ratings service in `westeurope` and customers complain it is slow. The finance system still lives in the company's on-premises data center and the new billing service must reach it without traversing the public internet. And during a flash sale, traffic hits one region hard while another sits idle. These are connectivity, performance, and distribution problems — and the right answer to each is a different Azure networking primitive. This module teaches you to tell them apart.

## Learning objectives

By the end of this module you will be able to:

- Recommend a connectivity solution that links Azure resources to the internet and to on-premises networks.
- Choose between VPN Gateway and ExpressRoute for hybrid connectivity based on bandwidth, latency, and privacy needs.
- Optimize network performance with peering, private endpoints, and content/application acceleration.
- Select a load-balancing and routing solution that matches the layer and scope of the traffic.

## Concepts

### Connectivity: getting traffic in, out, and across

A virtual network (VNet) is a private address space; by itself it talks to nothing outside. Three kinds of connectivity matter.

**Inbound from the internet** typically arrives through a public-facing service — Application Gateway, Azure Front Door, or a Load Balancer with a public IP — that you treat as the front door and secure deliberately. **Outbound to the internet** should be made explicit (for example through a NAT Gateway or firewall) so egress is predictable and auditable, not accidental. **Across VNets**, **VNet peering** connects two virtual networks so their resources communicate over Microsoft's backbone with low latency, as if on one network, without a gateway hop.

**Hybrid connectivity to on-premises** is the decision that trips up most designs, and it comes down to two options. A **VPN Gateway** builds an encrypted IPsec tunnel over the public internet — quick to stand up, lower cost, but subject to internet latency and variability. **ExpressRoute** provisions a private circuit through a connectivity provider that *never touches the public internet* — higher cost and longer lead time, but predictable latency, higher bandwidth, and a stronger compliance story. Choose VPN for modest, tolerant workloads; choose ExpressRoute when bandwidth, consistency, or "must not transit the internet" requirements dominate, as they do for Solstice's billing-to-finance link.

### Performance: shorten the path or keep it private

Latency is mostly distance and hops. Two levers reduce it.

First, **keep private traffic off the public internet.** A **private endpoint** projects an Azure PaaS service (a storage account, a database) into your VNet behind a private IP, so traffic to it stays on the Microsoft network and never exposes a public surface. This improves both security and consistency. Peering similarly keeps cross-VNet traffic on the backbone.

Second, **move the work closer to the user.** **Azure Front Door** is a global entry point that terminates connections at the edge near the user, caches static content, and routes dynamic requests over Microsoft's optimized backbone to the nearest healthy origin. For the cross-region pricing/ratings latency complaint, fronting the services with Front Door — or co-locating the chatty pair in one region — attacks the distance directly. The general principle: a request that travels less and hops less is faster, and most "the app is slow" network problems are really "the path is too long" problems.

### Load balancing and routing: pick the layer and the scope

Azure offers several load balancers, and the way to choose is a two-by-two: **what OSI layer** (4, TCP/UDP, versus 7, HTTP) and **what scope** (regional versus global).

- **Azure Load Balancer** — Layer 4, regional. Distributes TCP/UDP flows across backend instances. Use it for non-HTTP traffic or raw performance within a region.
- **Application Gateway** — Layer 7, regional. Understands HTTP, so it can route by URL path or host header, terminate TLS, and (with the WAF SKU) inspect requests. Use it for web traffic inside one region.
- **Azure Front Door** — Layer 7, global. HTTP routing plus edge acceleration and global failover across regions.
- **Traffic Manager** — DNS-based, global. Directs clients to an endpoint by returning different DNS answers (by performance, priority, or geography). It routes *resolution*, not packets, so it works for any protocol but cannot inspect requests.

The selection rule: HTTP and need path/header routing or a WAF → Application Gateway (regional) or Front Door (global). Non-HTTP → Load Balancer (regional) or Traffic Manager (global DNS). For Solstice's flash-sale imbalance across regions, a global Layer-7 distributor (Front Door) sends each user to the nearest healthy region and fails over automatically.

## Walkthrough: connecting Solstice billing to on-premises finance privately

Solstice's billing service must reach the on-premises finance system without traversing the public internet, and the security review requires that the connection be auditable. You recommend ExpressRoute for the circuit (private, predictable) and, as a first concrete step, establish the VNet and a gateway subnet that the gateway will later occupy. Here is the foundation expressed as Bicep so it is repeatable and reviewable:

```bicep
param location string = resourceGroup().location

resource billingVnet 'Microsoft.Network/virtualNetworks@2023-09-01' = {
  name: 'solstice-billing-vnet'
  location: location
  properties: {
    addressSpace: {
      addressPrefixes: [ '10.20.0.0/16' ]
    }
    subnets: [
      {
        name: 'billing-app'
        properties: { addressPrefix: '10.20.1.0/24' }
      }
      {
        // The gateway subnet MUST be named exactly 'GatewaySubnet'.
        name: 'GatewaySubnet'
        properties: { addressPrefix: '10.20.255.0/27' }
      }
    ]
  }
}

output gatewaySubnetId string = billingVnet.properties.subnets[1].id
```

Two design choices are load-bearing here. The subnet literally named `GatewaySubnet` is a hard Azure requirement — a VPN or ExpressRoute gateway will only deploy into a subnet with that exact name, and a `/27` leaves room for the gateway's address needs (verify the minimum size in the docs for your gateway SKU). Carving the gateway subnet now keeps the address plan clean before the circuit is provisioned. The billing app sits in its own subnet so you can later attach network security and routing rules to it independently. From here you would deploy the ExpressRoute gateway into `GatewaySubnet` and link the provisioned circuit — but the reviewable network skeleton is what makes that next step safe.

## Common pitfalls

- **Defaulting to VPN Gateway when the requirement says "private."** A VPN tunnel still rides the public internet. If the requirement is "must not transit the internet" or "predictable low latency at scale," that is ExpressRoute territory, despite the higher cost.
- **Naming the gateway subnet anything but `GatewaySubnet`.** Azure rejects gateway deployment into a differently named subnet. This is a common first-attempt failure that the Bicep above prevents.
- **Confusing a Layer-4 load balancer with a Layer-7 one.** Azure Load Balancer cannot route by URL path or terminate TLS; if you need host/path routing or a WAF, you need Application Gateway or Front Door. Picking the wrong layer means the routing rule you want simply cannot be expressed.
- **Leaving PaaS services on public endpoints out of habit.** A database reachable on a public IP is both a security surface and an inconsistent path. Private endpoints keep that traffic on the backbone and off the internet.
- **Solving a latency complaint with bigger compute.** If the real problem is two chatty services in different regions, scaling up the VM does nothing; shortening the path (co-location, peering, or edge acceleration) does.

## Knowledge check

1. A workload must reach an on-premises system with consistent low latency and a contractual guarantee that traffic never traverses the public internet. VPN Gateway or ExpressRoute, and why?
2. A web app needs to route `/api/*` to one backend pool and `/static/*` to another within a single region. Which load-balancing service can express that rule, and why can Azure Load Balancer not?
3. Customers worldwide hit a single-region app and distant users see high latency. Name two distinct network levers that reduce it.

<details>
<summary>Answers</summary>

1. ExpressRoute — it provisions a private circuit that does not use the public internet and offers predictable latency and bandwidth, satisfying both the consistency and the privacy requirements a VPN tunnel over the internet cannot guarantee.
2. Application Gateway (Layer 7, regional); Azure Load Balancer operates at Layer 4 and distributes by TCP/UDP flow, so it has no visibility into the URL path needed to route `/api/*` versus `/static/*`.
3. Move the work closer to users with an edge/global accelerator such as Azure Front Door, and/or shorten the path between services with co-location or VNet peering so requests travel less distance and fewer hops.

</details>

## Summary

Network design separates into three questions — how traffic connects (internet, hybrid, cross-VNet), how to make its path short and private, and how to distribute it — and each maps to a specific primitive chosen by layer and scope. VPN versus ExpressRoute, private endpoints versus public, and the load-balancer two-by-two are the decisions that decide whether a workload is reachable, fast, and compliant. With compute placed and the network designed, the next module, *Designing data storage solutions*, asks where the data those services read and write should actually live.

## Further learning

- [Choose a hybrid connectivity solution (VPN vs ExpressRoute)](https://learn.microsoft.com/en-us/azure/architecture/reference-architectures/hybrid-networking/)
- [Load-balancing options in Azure](https://learn.microsoft.com/en-us/azure/architecture/guide/technology-choices/load-balancing-overview)
- [What is Azure Private Link / private endpoints](https://learn.microsoft.com/en-us/azure/private-link/private-link-overview)
- [Azure Front Door overview](https://learn.microsoft.com/en-us/azure/frontdoor/front-door-overview)
