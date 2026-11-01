# Insmart AI — Product Development Plan & Design

**Version:** 1.0 · November 1, 2026
**Prepared by:** Insmart AI (Richard Lu)
**Status:** Product development plan and design document (Build Spec deliverable D1, per approved spec art_N0ARICWR). Every market number carries a source note in **Sources**. Where a claim could not be verified at a stated scope, the sourced replacement is used instead.

---

## Summary

Insmart AI estimates equipment health and failure risk from the maintenance records commercial HVAC operators already have — work orders, technician notes, manuals, asset inventories — instead of waiting on sensor retrofits. The MVP proves four commitments on real records: every risk score is **calibrated** and comes with honest uncertainty, the system **abstains** with a plain-language reason when the evidence is thin, every claim traces to a **provenance**-linked source record the technician can open, and diagnoses respect **physics constraints** for how equipment actually fails.

The beachhead customer is the HVAC service contractor and multi-site property owner running on years of work-order history and little instrumentation. That segment is large and structurally underserved: roughly 80% of U.S. commercial buildings have no building automation system for the records to compete with, and records-based AI copilots on the market stop at retrieval and drafting. The product plan below covers the problem and customer, the MVP capability set, competitive positioning against the closest threat (MaintainX Intelligence), what Phase I proves versus what comes after, and pricing grounded in comparable products.

## Load-bearing assumption

**The premise this plan rests on: records alone carry enough signal to rank diagnoses and justify action.** The supporting evidence is behavioral, not sensor-based — typical HVAC operators see first-time fix rates of 70–78%, meaning 22–30% of service calls need a second truck roll before resolution (Fieldproxy benchmarks, 2025; Fieldpie, 2026) [1][2] — which indicates the signal exists in dispatch and repair history, just unmined. **What would break it:** if the seed-corpus evaluation (spec art_N0ARICWR, Verification section) cannot beat a frequency-only baseline on adjudicated failure causes, the diagnosis layer needs either more data or sensor input, and the roadmap shifts accordingly. **What to check before committing further:** the Phase I hit@3 evaluation against baseline, and technician verdict rates on piloted cohorts.

**A second assumption, stated openly:** one founder can run an SBIR Phase I. This holds under SBIR rules (≥2/3 of work performed in-house, no co-PI), with Rutgers engaged as a subcontractor at ≤1/3 of budget. It reverses only if a committed Rutgers co-PI with an IP Rights Agreement appears — that flips the package to STTR.

## 1. Problem and ideal customer profile

### 1.1 The problem

Commercial HVAC operators sit on thousands of work orders that already contain the signal — repeat failures, aging equipment, deferred repairs, fixes that worked — and cannot mine it. The evidence base is fragmented across PDFs, ticketing exports, handwritten notes, and intermittent building-automation trends. Three structural facts define the gap:

**Most buildings have no instrumentation to fall back on.** Approximately 80% of U.S. commercial buildings lack digital HVAC controls — no building automation system, no smart thermostat coverage — per analysis of EIA CBECS 2018 data (Nexus Labs, October 2026) [3]. NREL (2022) found BAS adoption at nearly 60% for buildings over 50,000 sq ft but only 13% for buildings under 50,000 sq ft [4]; EIA's own trend study puts HVAC control coverage at roughly 70% of commercial *floorspace*, leaving about 30% of floorspace — dominated by small buildings — with nothing [5]. Even in instrumented buildings, monitoring typically covers central plant equipment; packaged rooftop units, terminal units, and pumps frequently report nothing.

**Sensor retrofits don't pencil out for most assets.** Consolidated 2026 estimates put installed first-year cost at $300–$1,200 for a small rooftop unit with basic sensors, but $5,000–$13,000+ for a chiller compressor, plus $500–$5,000 per site in integration work (IoT retrofit cost guides and market reports, 2026) [6][7][8]. More fundamentally, cheap sensor packages cover only a fraction of failure modes — a vibration sensor will not see refrigerant leaks, coil fouling, or controls faults [6]. Retrofit economics fail on exactly the low-criticality assets that make up most of a portfolio.

**The industry cannot hire its way out.** Industry estimates put unfilled HVAC technician positions at roughly 110,000 (2025–26), against a workforce averaging ~55 years of age; BLS projects about 42,500 annual openings for HVAC mechanics and installers, 2023–2033 [9][10][11]. Triaging records manually consumes the scarcest resource in the trade.

The cost of getting this wrong is real but must be stated at its sourced scope: unplanned downtime costs U.S. *industrial* operators an estimated $50B per year (Deloitte, 2017, cited in Honeywell's 2024 white paper; ~$64B inflation-adjusted to 2024) [12]; U.S. HVAC services and repair spending runs roughly $14B per year (Oxmaint industry analysis, February 2026) [13]; and a single commercial HVAC failure event can cost $15,000–$70,000 including emergency labor and tenant disruption (vendor content estimate — directional only) [14]. No authoritative source isolates a national commercial-HVAC failure cost figure, and Insmart AI does not claim one.

### 1.2 Ideal customer profile

**Beachhead:** HVAC service contractors and multi-site property owners with (a) at least two years of digitized work-order history, (b) portfolios heavy in rooftop units, split systems, and AHUs, and (c) little or no BAS instrumentation across most of the portfolio. The user is the service manager or senior technician; the buyer is the operations or facilities leader. Secondary: property owners who want portfolio-level visibility of assets heading toward failure and capital-planning output for board cycles.

**Why this ICP buys.** The metrics they already track move with our product: first-time fix rate (typical operators run 70–78%, so 22–30% of visits are repeats — Fieldproxy, 2025; Fieldpie, 2026) [1][2], and avoidable return visits at a fully loaded cost of roughly $650 each (FacilityManagement.com, September 2026; direct truck-roll cost $450–$1,000) [15][16]. Contractors already pay $250–$400 per technician per month for ServiceTitan or similar field-service software (industry benchmarks, 2026) [17], so a diagnostics layer priced per asset fits an existing budget line rather than creating a new one.

**Why now.** The labor shortage makes technician throughput the binding constraint [9][10], and CMMS vendors have just begun shipping AI on records — which both validates the category and leaves the hard part unclaimed (Section 3).

## 2. MVP capability set

The MVP is a demonstration of feasibility on a seed corpus (~150 synthetic HVAC work orders across ~20 assets, with adjudicated ground truth) — not yet a commercial pilot. Its five capabilities, in the order a customer experiences them:

1. **Bulk ingestion.** Upload a CSV work-order export (or PDF bundle); the parser normalizes it to a canonical work-order shape. Unparseable rows land in a review list with reasons — never silently dropped. Value appears in week one, with no integration project.

2. **Cited asset timelines.** For any asset, a reconstructed "what happened to this RTU before" view in which every entry links to its source record. Contradictions (e.g., "compressor replaced 2023" vs. "compressor original 2011") surface side-by-side with both sources rather than being resolved silently.

3. **Repeat-failure views.** A portfolio leaderboard of assets with recurrence counts and repeat-callback patterns — the productized form of the $650-per-return-visit problem [15].

4. **Ranked diagnosis with abstention.** The core research claim, expressed as a strict contract: a diagnosis request returns either **ranked** causes, each with a confidence and at least one cited observation, or an explicit **insufficient-evidence** state with a plain-language reason ("2 usable records for this asset") and what would help. No UI surface ever renders a confidence number for an abstention; tests enforce this. Physics constraints enter as an explicit, inspectable priors module (e.g., compressor failures co-occur with low suction pressure; refrigerant leaks are seasonal) rather than a black-box model.

5. **Technician feedback capture.** Every diagnosis accepts confirm / correct / reject with an optional note. This loop is the moat: each verdict is outcome-labeled training data competitors without deployments do not have.

Architecture note (full detail in the build spec, art_N0ARICWR): FastAPI + SQLAlchemy/SQLite backend, React/Vite frontend, an LLM extraction provider behind an interface with a deterministic rule-based fallback so the entire test suite runs without an API key. One table per concept in an evidence graph, provenance attached to every row — no inference exists without evidence ids resolving to real observations.

**Out of scope for this build, deliberately:** sensor ingestion, failure-date forecasting, and work-order authoring. Each is Phase II material (Section 4).

## 3. Competitive positioning

### 3.1 Where we sit in the landscape

The full 17-vendor comparison lives in the market research artifact (art_OBSFEMtB, Section 2). Four categories surround our position:

**Sensor-heavy predictive maintenance** (Augury, Samotics, Siemens Senseye, Tractian/Waites). All require installed hardware or dense existing time-series. They cannot serve our segment without abandoning their model — Augury's economics depend on installing its own sensors [18]; Samotics requires electrical-panel hardware [19]. Not competitors for records-only portfolios; validation for the market direction.

**Building analytics / FDD platforms** (Facilio, Nantum, Desigo, 75F, PassiveLogic). All require BAS points that ~80% of commercial buildings do not have [3]. They serve the instrumented 20%; we serve the un-instrumented 80%.

**CMMS platforms** (Fiix, UpKeep, Limble, eMaint). They hold the records and ship scheduling plus descriptive analytics; their AI layers draft text and answer questions. Priced $20–$75 per user per month on published tiers (vendor pricing via comparison sites, 2026) [20].

**Records-based AI copilots — the category that matters.** This is where the real competition is, and it is funded, real, and moving.

### 3.2 The closest competitor and our response

**MaintainX Intelligence is the named closest competitor.** MaintainX raised at unicorn scale and ships "Intelligence" features including failure prediction and parts-demand forecasting on top of existing work-order data, at ~$20–$65 per user per month on the tiers that carry AI (MaintainX review, Opmaint, July 2026) [21]. UpKeep Nova AI, GMAO Copilot (HVAC-specific, from €20/month), and Microsoft Dynamics 365 Field Service Copilot occupy adjacent ground [20][22][23]. The old claim that "CMMS platforms are passive ticketing repositories with zero predictive intelligence" is no longer accurate, and this plan does not make it.

**What none of them ship — and where this product lives.** Across all vendor materials reviewed (art_OBSFEMtB, Section 4): no records-based product pairs diagnosis with **calibrated** failure probabilities, **physics-constrained** causal ranking, or **explicit abstention** — the distinction between "low risk" and "insufficient evidence." Retrieval and drafting are table stakes; calibrated risk with provenance is the layer everyone skips. A confident wrong answer from a copilot costs a contractor nothing but trust; one that sends a technician in front of a live chiller ends the deployment. Our differentiation commitments are precisely the parts incumbents' architectures do not surface.

**The response to MaintainX, concretely:**

- **Wedge with depth, not breadth.** MaintainX must serve every trade generically. We win one equipment family (commercial HVAC) with diagnosis quality a generic copilot cannot match — ranked causes, calibrated confidence, physics priors, cited evidence — and expand from there.
- **Own the safety boundary.** Abstention is both the research contribution and the trust feature. We make "insufficient evidence" a first-class product state; retrieval-grade copilots structurally cannot, because their contract is always to answer.
- **Move first on the feedback loop.** Every technician verdict on our system is labeled outcome data. A copilot incumbent with millions of work orders but no verdict-capture loop has distribution; we accumulate the evaluation asset. The MVP's feedback capture is designed for exactly this.
- **Be honest about the window.** An incumbent could add probabilistic risk scoring. The defense is speed to the calibration/abstention layer plus the outcome data loop — which is why the MVP ships feedback capture in its first build rather than later.

## 4. Post-MVP roadmap

**What Phase I proves (months 1–12, per the proposal draft fl_YZr7h4H7):** that evidence-grounded inference from sparse records is feasible and technically de-risked — evidence-graph construction with provenance (WP1), risk estimation under sparse observations with calibration (WP2), physics-aware causal ranking with abstention (WP3), and retrospective plus shadow-mode validation against rule-based, retrieval-RAG, and conventional ML baselines (WP4). Phase I evidence is feasibility and technical risk reduction, not revenue. Headline evaluation targets: diagnosis hit@3 beating a frequency baseline on adjudicated seed data, extraction precision/recall ≥ 0.8 on the deterministic extractor, and abstention correctness on thin-history assets (spec art_N0ARICWR, Verification).

**What comes after Phase I, gated on those results:**

1. **Failure-date forecasting** — moving from ranked causes to time-to-failure estimates, which requires the calibrated survival machinery WP2 builds plus outcome data the feedback loop accumulates. Only justified once hit@3 and verdict rates demonstrate signal.
2. **Sensor fusion where telemetry exists** — the same evidence graph accepts BAS trend points and cheap sensor data as additional observations. This is the expansion path into the partially instrumented 20% [3][4], not a pivot: records remain the backbone, sensors enrich it.
3. **Adjacent verticals** — refrigeration, industrial pumps, elevators, and data-center cooling, in that order of equipment-family similarity to HVAC. The representation generalizes; each vertical needs its own physics priors module and adjudicated corpus.
4. **Workflow depth** — service-agreement pricing analytics and dispatch qualification, informed by the outcome data loop.

Each stage consumes the moat built by the one before it: the feedback corpus makes forecasting trainable, forecasting makes sensor fusion worth instrumenting for, and validated calibration makes vertical expansion a sales argument rather than a research project.

## 5. Pricing and go-to-market

### 5.1 Where comparables land

Per-asset and per-seat benchmarks from the market research (art_OBSFEMtB, Section 5; sources are comparison-site and vendor-list figures — indicative list prices, not transacted prices):

| Comparable | Price | Source |
|---|---|---|
| Basic smart-building monitoring | $2–$5/asset/mo ($24–$60/yr) | 2026 benchmark synthesis [24] |
| Monitoring + anomaly detection | $5–$12/asset/mo ($60–$144/yr) | Same [24] |
| Work-order intelligence / diagnostics tier | $8–$20/asset/mo ($96–$240/yr) | Same [24] |
| MaintainX / UpKeep / Fiix / Limble CMMS+AI | $20–$75/user/mo | Vendor tiers via comparison sites [20][21] |
| ServiceTitan (field-service platform) | ~$250–$400/technician/mo | Industry benchmarks, 2026 [17] |
| Enterprise FDD, single campus | $90,000–$180,000 deployment | Svitla Systems, 2026 [25] |

### 5.2 Our price

**$8–$12 per asset per month core, $15 per asset per month with advanced diagnostics, with a $15,000 annual portfolio minimum** — squarely inside the work-order-intelligence band ($96–$240/asset/yr) [24], which is the correct comparable class for a records-based diagnostics product. The original draft's $150–$300/asset/yr is retired: its top end exceeds every per-asset benchmark found except controls-tied platforms [24]. Portfolio minimums matter more than the per-asset number — a 100-asset pilot at $10/asset/mo is $12,000/yr, below any supportable cost to serve, hence the $15,000 floor.

**Pilot structure:** paid, narrow, 60–120 day pilots of 3–10 buildings or 50–300 assets at $10,000–$30,000 fixed fee, credited against conversion, with pre-agreed success criteria (diagnosis hit@3 against senior-tech conclusions on closed work orders, repeat-visit reduction, triage time) and a written conversion decision before the pilot starts. Free "feedback-only" pilots are a documented failure pattern in the GTM literature [24]. Phase I budgets assume validation costs, not revenue — the paid structure exists to test willingness to pay, the thing the proposal draft flags as unvalidated [26].

**Channel:** implementation-plus-reseller through service contractors at a 20–30% recurring margin, with the contractor bundling the product into maintenance agreements [24]. The structural tension is named rather than ignored: software that cuts emergency callouts threatens a revenue line contractors live on. The positioning answer is *more productive service revenue* — better-qualified dispatches, billable preventive work sold from detected degradation, higher technician throughput against the 110,000-person shortage [9] — which is also where the technology's evidence (repeat failures, emerging degradation) points.

### 5.3 Success metrics

- **Phase I (feasibility):** hit@3 ≥ frequency baseline on adjudicated seed data; extraction precision/recall ≥ 0.8 (deterministic extractor); abstention correctness on thin-history assets; demo runbook passes for a reviewer with no context (spec art_N0ARICWR).
- **First pilots (commercial):** ≥25% triage-time reduction on piloted cohorts (the proposal's headline target [26]) and first-time-fix-rate improvement — the metric contractors already track and believe [1][2].

## Sources

Market claims trace to the market and competitive landscape research (art_OBSFEMtB, conducted November 1, 2026), which verified each claim against the underlying sources below. Numbers without an external source note are internal design targets, not market facts.

[1]: Fieldproxy, Field Service Industry Benchmarks Calculator (2025) — https://www.fieldproxy.ai/benchmarks
[2]: Fieldpie, "HVAC First-Time Fix Rate: How to Reduce Repeat Visits" (2026) — https://www.fieldpie.com/blog/hvac-first-time-fix-rate/
[3]: Nexus Labs, "84% don't have a BAS?" — CBECS 2018 analysis (October 2026) — https://www.nexuslabs.online/content/84-don-t-have-a-bas-nexus-newsletter-100
[4]: NREL, Commercial Building Sensors and Controls Systems (2022) — https://docs.nrel.gov/docs/fy22osti/82750.pdf
[5]: EIA, Trends in Commercial Whole-Building Sensors and Controls (CBECS 2018 base) — https://www.eia.gov/analysis/studies/buildings/commercial/sensors/pdf/sensors_controls.pdf
[6]: Oxmaint, "IoT HVAC Sensors Guide" (March 2026) — https://oxmaint.com/industries/hvac/iot-hvac-sensors-monitoring-guid
[7]: Oxmaint, "Predictive Maintenance for HVAC: Sensors & Analytics" (July 2026) — https://oxmaint.com/blog/post/hvac-predictive-maintenance-sensors-analytics
[8]: The Machine Daily, "How to Evaluate HVAC IoT Sensor Maintenance" (July 2026) — https://themachinedaily.com/mfg-general/carrier-hvac-iot-sensor-maintenance-evaluation
[9]: Oxmaint, "Climate Control Service Fleet Dispatch and Scheduling" (2026) — https://oxmaint.com/industries/hvac/climate-control-service-fleet-dispatch-scheduling
[10]: Workyard, "75+ HVAC Industry Facts and Statistics" (2026) — https://www.workyard.com/construction-management/hvac-facts-statistics
[11]: U.S. Bureau of Labor Statistics, Occupational Outlook — HVAC Mechanics and Installers (2023–2033 projections) — https://www.bls.gov/ooh/installation-maintenance-and-repair/heating-air-conditioning-and-refrigeration-mechanics-and-installers.htm
[12]: Honeywell white paper citing Deloitte (2017) unplanned-downtime estimate (2024) — https://hbtmkto.honeywell.com/rs/127-UCB-316/images/Predictive-Maintenance-White%20Paper2024.pdf — *industrial scope, not commercial HVAC*
[13]: Oxmaint, "HVAC Preventive vs Reactive Maintenance" (February 2026) — https://oxmaint.com/industries/hvac/hvac-preventive-vs-reactive-maintenance
[14]: Oxmaint, "Common HVAC Failures in Commercial Buildings" (March 2026) — https://oxmaint.com/industries/facility-management/common-hvac-failures-in-commercial-buildings-and-how-to-prevent-them — *vendor content estimate; directional only*
[15]: FacilityManagement.com, "The Hidden Cost of Return Visits in HVAC Service Businesses" (September 2026) — https://facilitymanagement.com/hvac-service-hidden-cost/
[16]: Oxmaint case study (2026), via art_OBSFEMtB — direct truck-roll cost $450–$1,000
[17]: BDR & Co., "The Guide to HVAC Business Software in 2026" (June 2026) — https://www.bdrco.com/blog/hvac-business-software-guide/ ; SelectHub ServiceTitan vs BuildOps — https://www.selecthub.com/field-service-software/servicetitan-vs-buildops/
[18]: Augury, "Machine Health Solutions" (2026) — https://www.augury.com/lp/predictive-maintenance/
[19]: Samotics, via Frostlogic platform comparison (July 2026) — https://www.frostlogic.se/articles/industrial-sensor-intelligence-platforms/
[20]: Rankite, "Top Asset Management Software in 2026" (October 2026) — https://rankite.com/blog/top-asset-management-software ; "Best Work Order Management Software in 2026" — https://rankite.com/blog/best-work-order-management-software
[21]: Opmaint, "MaintainX Review 2026" (July 2026) — https://www.opmaint.com/blog/maintainx-review/
[22]: Capterra, "GMAO Copilot Software" — https://www.capterra.com/p/10041827/GMAO-Copilot/
[23]: Omid Saffari, "Best AI Assistants for Field Service Technicians 2026" (August 2026) — https://omidsaffari.com/blog/best-ai-assistants-for-field-service-technicians-2026
[24]: Smart-building / facility-tech pricing and GTM benchmark synthesis (compiled from vendor and comparison-site research, November 1, 2026), including https://www.business-software.com/blog/hvac-service-agreement-software/ and https://buildops.com/resources/hvac-automation-software — *synthesis, not a single primary source; treat bands as indicative*
[25]: Svitla Systems, "Fault Detection and Diagnostics Software" (October 2026) — https://svitla.com/industry-solutions/fault-detection-and-diagnostics-software-we-provide/
[26]: Insmart AI, NSF SBIR/STTR Phase I proposal working draft (October 24, 2026) — project file fl_YZr7h4H7

**Internal artifacts referenced:** Build Spec art_N0ARICWR (MVP, test plan, NSF package — approved November 1, 2026); Market & Competitive Landscape art_OBSFEMtB (17-vendor comparison, claims verification table, pricing analysis).
