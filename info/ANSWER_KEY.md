# Answer Key — Design Intent of the 15 Orders

> ⚠️ **Build first, peek later.** This file documents what each order is *testing*
> and the expected agent behavior. Reading it before you build will rob you of the
> real exercise (you'd hardcode to it, which is explicitly disallowed). Use it to
> self-grade after your first end-to-end pass, or if you get stuck.

The catalog (`data/catalog.csv`, 874 SKUs) is intentionally messy: inconsistent
naming, mixed ES/EN, blank brands/vehicles, supersessions, price-format chaos,
duplicates, and near-duplicate traps. Customer messages are realistic
(Spanish / Spanglish), because cross-language matching is part of the difficulty.

| # | What it tests | Trap / difficulty | Expected good behavior |
|---|---------------|-------------------|------------------------|
| 01 | Clean baseline | None — happy path | Match `SKU-1001` (Oil Filter Corolla 2015), high confidence, quote, done. No questions. |
| 02 | Underspecified part type | "el filtro" — oil? air? fuel? cabin? | **ASK** which filter. Do NOT silently pick one. A good agent lists the options it found for that vehicle. |
| 03 | Multi-item + variant ambiguity | "un par de amortiguadores" — front or rear? Catalog has both (`SKU-1011/1012`). Brake pads are unambiguous (`SKU-1010`). | Resolve pads confidently; **ASK** front/rear for shocks (or quote both and label clearly). Two line items minimum. |
| 04 | Typos + cheapest intent | "pra corola" (typos), "economico" | Fuzzy-match to Corolla 2015 air filter; among matches pick the lowest-priced (`SKU-1003` over `SKU-1004`) and justify. |
| 05 | Supersession / discontinued | Old Versa clutch (`SKU-1021`) is `replaced_by` `SKU-1020` and marked `descontinuado` | Recognize the discontinued ref and **offer the replacement** `SKU-1020`, explaining it supersedes the old one. |
| 06 | Regional slang | "balineras" = wheel bearings; "de adelante" = front; "las dos" = qty 2 | Map slang → wheel bearing; match front Logan bearing (`SKU-1030`); quantity = 2. |
| 07 | **Image input** | Photo of a spark plug marked "NGK CR8E", no vehicle stated | Read the image, identify it as a spark plug, match by OEM `CR8E` → `SKU-1040`/`SKU-1091`. If vehicle matters for confirmation, note the assumption. |
| 08 | Conflicting requirements | Wants "la iridium la buena" AND "la mas economica" — mutually exclusive (`SKU-1041` iridium vs `SKU-1040` standard) | Surface the conflict; quote BOTH, explain the trade-off, let the human choose. Don't silently resolve. |
| 09 | Quantity inference | "aceite para el cambio" Hilux 2018 diesel — how many liters? | Match diesel oil `SKU-1050`; infer/confirm engine oil capacity (~6.5L). Either compute quantity from capacity or **ASK** if unsure. Must NOT match the gasoline 5W-30. |
| 10 | Universal item, spec ambiguity | "refrigerante" — concentrate vs pre-mixed (`SKU-1060` vs `SKU-1061`), no vehicle | No vehicle needed, but **ASK** concentrate vs ready-to-use, or present both. |
| 11 | Job → bill of materials | "sincronizacion completa" Spark 2015 = a *set* of parts, none named | Infer a tune-up kit: spark plugs (`SKU-1072`), air filter (`SKU-1071`), oil filter (`SKU-1070`), engine oil. Assemble a multi-line order and state the assumption. |
| 12 | Out-of-catalog | Ford Fiesta — **no Ford in catalog** | Say it's not available. Do NOT hallucinate a SKU. Optionally offer to special-order or ask for an alternative. |
| 13 | OEM-code lookup | Customer gives only `90915-YZZD4`, qty 4 | Match by `oem_cross_ref` → `SKU-1001`/`SKU-1002`. Note there are two SKUs sharing that OEM (duplicate) and pick/flag. Quantity = 4. |
| 14 | Near-duplicate trap | "disco delantero" Mazda 3 2016 — ventilado (front, `SKU-1080`) vs solido (rear, `SKU-1081`) | "Delantero" disambiguates → ventilado `SKU-1080`. A naive matcher grabs the wrong one. |
| 15 | Bulk + stock + (hour-5 hook) | Multi-line fleet order; `SKU-1092` chain kit is `agotado`, `SKU-1091` low stock (2) vs requested 10 | Quote all lines; **flag the out-of-stock chain kit and the insufficient bujia stock**; propose partial fulfillment or alternatives. Don't quietly promise stock you don't have. |

## Scoring anchors (what "robust" means here)
- An agent that asks a clarifying question on **02, 03(shocks), 10** and confidently
  resolves **01, 04, 06, 13, 14** is hitting the preguntar-vs-asumir balance.
- An agent that hallucinates a SKU for **12**, or matches gasoline oil for **09**,
  or silently picks one bujia for **08**, is failing the core test.

## The Hour-5 surprise (give it to yourself at the 5-hour mark, not before)
> "Client update: from now on every quote must also return an **estimated margin**.
> The catalog only has a sell `price` — assume cost = 70% of price for parts and
> 85% for fluids/oils. Also, for any line that is out of stock, the system must
> automatically suggest the closest in-stock alternative SKU (same category +
> vehicle), not just flag it."

This forces a schema change + a new matching pass late in the build. Handle it
without breaking what already works.
