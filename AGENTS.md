cat << 'EOF' > ANTIGRAVITY_FOUNDRY_INTEGRATION.md
# ANTIGRAVITY_FOUNDRY_INTEGRATION.md

## Project Modernization and Palantir Foundry Architectural Integration Specification

### 1. Executive Summary and Refactoring Target

The objective of this specification is to guide an automated AI coding agent (such as Antigravity, Cursor, or Windsurf) through upgrading the `M_PROJECT` fast-fashion e-commerce repository. The baseline system relies on static HTML5 pages, inline JavaScript, legacy jQuery components, and browser-bound `localStorage`.

This project will be refactored into a full-stack, decoupled Web application (Next.js App Router, TypeScript, Node.js, Tailwind CSS) backed by an Enterprise Data Layer inspired by Palantir Foundry architectural capabilities, including an Enterprise Ontology, supply chain digital twin, dynamic pricing engines, reverse logistics anomaly detection, Customer 360 recommendation modules, and Scope 1–3 carbon accounting engines.

---

## 2. Technical System Architecture

* **Client Presentation Layer**: Next.js (App Router), React, Tailwind CSS, Server-Side Rendering (SSR).
* **API Gateway & Security Layer**: OAuth2 / JWT authentication middleware with Purpose-Based Access Control (PBAC).
* **Enterprise Data Layer**: PostgreSQL (via Prisma ORM) housing the Retail Ontology (SKU, Store, COGS Ledger, Reverse Logistics, Customer 360).
* **State & Cache Management**: Redis Cluster for active shopping cart sessions and token persistence.

---

## 3. Detailed Operational Modules to Implement

### Module 1: Core Framework Refactoring and Secure State Synchronization

* **Baseline Issue**: Cart data and user states are stored unsecured in browser `localStorage`, causing security vulnerabilities and session loss across devices.
* **Target State**:
  * Migrate all static `.html` files (`HomePage.html`, `cart.html`, `payment.html`) into Next.js Server-Side Rendered (SSR) routes.
  * Implement Redis for server-side cart session storage linked via encrypted HttpOnly JWT cookies.
  * Enforce Purpose-Based Access Control (PBAC) across all API routes to ensure secure data handling.

### Module 2: Enterprise Data Layer and Supply Chain Digital Twin

* **Target State**:
  * Define a standardized data backplane representing physical retail assets: `SKU`, `StoreLocation`, `InventoryBatch`, `Supplier`, `PurchaseOrder`, and `TransitNode`.
  * Implement real-time inventory tracking that mirrors warehouse and physical store shelf levels.
  * Calculate granular item-level Cost of Goods Sold (COGS) by dynamically allocating freight surcharges, warehousing costs, and labor overhead down to atomic SKU units.
  * Expose live stock availability indicators on product detail pages.

### Module 3: Dynamic Pricing, Elasticity, and Promotion Simulation Engine

* **Target State**:
  * Replace hardcoded static pricing attributes with an algorithmic dynamic pricing engine.
  * Calculate real-time price elasticity based on local inventory velocity, competitor web scrape feeds, and storage cost parameters.
  * Build an operational approval interface for category managers (modeled after Palantir Workshop) to review, edit, and approve dynamic price proposals with human-in-the-loop validation.
  * Add campaign back-testing controls to simulate promotional margin performance prior to campaign launches.

### Module 4: Reverse Logistics and Vendor Contract Anomaly Detector

* **Target State**:
  * Construct an automated returns management portal in the customer account area.
  * Implement an anomaly detection engine that parses unstructured vendor contract terms to check warranty allowances, return thresholds, and restock policies.
  * Determine optimal item disposition routes (e.g., return to shelf, ship to refurbish hub, liquidate, or initiate vendor chargeback) to reduce handling costs and maximize financial recovery.

### Module 5: Omnichannel Customer 360 and AIP Personalization Engine

* **Target State**:
  * Unify e-commerce clickstream analytics, purchase history, store visits, and support logs into centralized Customer 360 profiles.
  * Deploy a Next Best Offer (NBO) marketing module that surfaces personalized product bundles and tailored discount vouchers directly on user feeds.
  * Integrate AI agents powered by Palantir AIP design concepts to provide automated customer support and smart shopping assistance.

### Module 6: Scope 1–3 Sustainability and Waste Markdown Engine

* **Target State**:
  * Calculate lifecycle Scope 1, 2, and 3 greenhouse gas emissions per SKU across manufacturing, transit, and packaging.
  * Display sustainability transparency scores and low-emission delivery choices during checkout.
  * Deploy perishable waste reduction algorithms that adjust clearance markdowns automatically based on product shelf life to reduce inventory write-offs.

---

## 4. Antigravity Implementation Task Matrix

| Task ID | Component Name | Target File / Area | Action Required | Operational Outcome |
| :--- | :--- | :--- | :--- | :--- |
| **TSK-01** | Next.js Refactor | `/pages` or `/app` | Convert legacy HTML/jQuery markup into Next.js React components. | High-speed SSR pages with reduced load times. |
| **TSK-02** | Session Infrastructure | `/api/cart` & Redis | Replace `localStorage` operations with authenticated Redis session endpoints. | Zero client-side data tampering; cross-device cart retention. |
| **TSK-03** | Retail Ontology Schema | `/prisma/schema.prisma` | Define schemas for `SKU`, `Store`, `COGS`, `Supplier`, and `InventoryBatch`. | Digital twin database abstraction. |
| **TSK-04** | Dynamic Pricing API | `/api/pricing/dynamic` | Implement price elasticity calculation algorithm with real-time COGS inputs. | Margin protection and automated price adjustments. |
| **TSK-05** | Pricing Admin UI | `/admin/pricing` | Build human-in-the-loop review dashboard using Tailwind UI widgets. | Category managers approve or override automated price suggestions. |
| **TSK-06** | Reverse Logistics | `/api/returns/process` | Create return anomaly checking logic against vendor contract policies. | Lower disposal costs and automated supplier chargebacks. |
| **TSK-07** | Customer 360 NBO | `/components/recommendations` | Render personalized product feeds based on customer affinity vectors. | Increased average order value (AOV) and conversion lift. |
| **TSK-08** | ESG Emissions Engine | `/api/checkout/emissions` | Compute Scope 1–3 carbon scores per order and present eco-shipping options. | Complete corporate ESG transparency and consumer trust. |

---

## 5. Execution Instructions for Antigravity AI Agent

When executing tasks in this codebase, follow these rules:

1. **Incremental Refactoring**: Execute refactoring tasks in sequence (`TSK-01` through `TSK-08`). Ensure all unit tests pass before moving to the next task.
2. **TypeScript Strictness**: Enforce strict TypeScript typing for all data models corresponding to Enterprise Ontology objects (`SKU`, `Store`, `COGS`, `Customer360`).
3. **No Unencrypted Client State**: Never store transactional session data, payment details, or pricing calculations in client-side storage primitives like `localStorage` or `sessionStorage`.
4. **Data Validation**: Ensure all write-back actions to the PostgreSQL database validate purpose-based security permissions (PBAC).
5. **Component Standards**: Use accessible, semantic React components adhering to WCAG 2.1 AA design guidelines.
EOF