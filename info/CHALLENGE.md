# 🔧 Hackathon Challenge — "The Invisible Bottleneck"

**Format:** Individual · **Time box:** 6 hours · **Theme:** AI solutions for real businesses

---

## 1. The business

**RepuExpress** is a fictional-but-realistic auto & motorcycle parts distributor in
Colombia. ~40 employees. Orders arrive through three channels — **WhatsApp, email,
and a web form** — and they arrive as *messy natural language*: half Spanish, half
Spanglish, full of typos, slang, missing details, and sometimes a **photo** of the
part instead of a name ("necesito el filtro del Corolla 2015", "me sirve esta? [foto]").

Today, three employees spend their entire day **manually translating that chaos** into
structured orders in the ERP, looking up the right SKU in an 874-item catalog, quoting,
and replying. It's slow (hours of latency), error-prone (wrong SKUs = wrong quotes =
returns), and it doesn't scale. They lose sales because they reply too late.

## 2. Your mission

Build an **AI agent** that ingests a raw customer order (text and/or image) and turns it
into a **structured, quote-ready order with an automatic customer reply** — handling
ambiguity the way a sharp salesperson would, not the way a rigid web form does.

The hard part is **not** parsing clean input. It's:

1. **Cross-language, fuzzy semantic matching** against a deliberately messy catalog
   where the customer's words almost never match the catalog text literally.
2. **The ask-vs-assume decision.** An agent that asks about everything is useless. One
   that assumes everything quotes wrong and costs the business money. *Walking that line,
   and being able to justify each call, is the heart of this challenge.*

## 3. What you're given

```
parts-hackathon/
├── CHALLENGE.md          ← this file
├── ANSWER_KEY.md         ← design intent per order (DON'T read until you've built)
└── data/
    ├── catalog.csv       ← 874 SKUs, intentionally messy
    └── orders/
        ├── order_01.txt … order_15.txt   ← 15 raw customer messages
```

### `catalog.csv` columns (and why they're hostile)
`sku, name, brand, category_hint, vehicle_make, vehicle_model, year, oem_cross_ref,
replaced_by, price, stock, notes`

- **`name`** — the same concept is written many ways across rows: `Oil Filter`,
  `Filtro de Aceite`, `FILTRO DE ACEITE`, `O.Filter`, `Filtro Ac.`… Brand and vehicle
  appear as prefix, suffix, or not at all. Some names have typos.
- **`brand`, `vehicle_make`, `vehicle_model`, `year`, `category_hint`** — **frequently
  blank.** You cannot rely on them being populated.
- **`oem_cross_ref`** — OEM/aftermarket cross numbers in inconsistent formats; sometimes
  the only reliable join key (see order 13).
- **`replaced_by`** — supersession. Sometimes filled with a newer SKU; sometimes the
  supersession is *only* mentioned in `notes` ("reemplazado por SKU-XXXX"); sometimes
  marked `descontinuado`.
- **`price`** — formats are inconsistent on purpose: `18500`, `$ 18.500`, `COP 18500`,
  `18500.00`. **You must normalize before quoting.**
- **`stock`** — integers, but also `""`, `0`, `agotado`, `few`. Normalize it.
- **There are duplicates** (same part, different SKU) and **near-duplicate traps**
  (names look identical but differ in a critical spec like front/rear or
  ventilado/solido). Naive string matching will pick the wrong one.

### `orders/*.txt`
Each file has a small header (`CHANNEL`, `FROM`, sometimes `SUBJECT`/`ATTACHMENT`) and a
`---` separator, then the raw message. **`order_07.txt` is the image case** — for this
exercise the photo is described in-line in `[IMAGE DESCRIPTION ...]` brackets; in a real
deployment that would be an actual image file, so architect the image path as if a vision
model will receive real pixels (don't just grep the bracket text — treat it as the
output of a vision step).

> **Why is the data bilingual?** Because the real RepuExpress is. Forcing English-only
> data would delete the single most important difficulty. Your *code, logs, and the
> structured output schema* should be in English; the *matching* must survive Spanish input.

## 4. Required output (per order)

For every order your agent processes, produce a structured object roughly like:

```json
{
  "order_id": "order_03",
  "channel": "email",
  "line_items": [
    {
      "customer_text": "pastillas de freno",
      "matched_sku": "SKU-1010",
      "matched_name": "Pastillas de Freno Renault Duster 2016",
      "quantity": 1,
      "unit_price": 68000,
      "confidence": 0.93,
      "decision": "auto_matched",
      "reasoning": "Brake pads + Duster 2016 → single confident match."
    },
    {
      "customer_text": "un par de amortiguadores",
      "matched_sku": null,
      "quantity": 2,
      "confidence": 0.40,
      "decision": "needs_clarification",
      "reasoning": "Catalog has front (SKU-1011) and rear (SKU-1012) shocks for Duster; customer didn't specify.",
      "clarifying_question": "¿Los amortiguadores son delanteros o traseros?"
    }
  ],
  "questions_for_customer": ["¿Los amortiguadores son delanteros o traseros?"],
  "customer_reply_draft": "Hola, ya te cotizo las pastillas ($68.000). Para los amortiguadores, ¿los necesitas delanteros o traseros?",
  "quote_total_partial": 68000
}
```

The exact schema is yours — but every line item must expose **(a)** the matched SKU (or
null), **(b)** a confidence, **(c)** an explicit `decision` (e.g. `auto_matched` /
`needs_clarification` / `not_found`), and **(d)** human-readable `reasoning`. The
`decision` + `reasoning` are what the judges read to evaluate your ask-vs-assume logic.

## 5. Rules (read carefully — these are anti-cheese rules)

1. **No hardcoding to the 15 orders.** At demo time you'll be handed *new* orders. If
   your matching is a lookup table keyed on the sample messages, you score ~zero on
   robustness. Build a general matcher.
2. **No hallucinated SKUs.** If nothing fits (order 12), say so. Inventing a plausible
   SKU is the worst possible failure for a parts business.
3. **You must handle the image order** (07) through a real vision step in your
   architecture, not by string-reading the description.
4. **Normalize prices and stock** before quoting.
5. **Expose your ask-vs-assume reasoning** in the output — a silent black box can't be
   judged on the dimension that matters most.
6. **At the 5-hour mark, inject the surprise requirement** (bottom of `ANSWER_KEY.md`,
   or have a friend reveal it). It changes the output schema and adds a matching pass.
   This simulates a real mid-project client change.

## 6. Scoring (100 pts)

| Dimension | Weight | What earns points |
|-----------|-------:|-------------------|
| **Robustness to ambiguity** | 35 | Sensible behavior on garbage, partial, slang, and unseen input; graceful "not found"; no hallucinations. |
| **Semantic match quality** | 25 | Correct SKU across language/format gaps; survives blank fields; resists near-duplicate & supersession traps. |
| **Ask-vs-assume logic** | 20 | Asks only when value of asking > cost; assumes confidently when safe; *every* decision is justified. |
| **End-to-end demo** | 15 | Runs live on new orders, text→structured→quote→reply, no babysitting. |
| **Business viability** | 5 | Would this actually save RepuExpress time/money? Latency, accuracy, handoff to a human. |

**Tie-breaker / bonus:** clean handling of the hour-5 surprise without breaking earlier
behavior.

## 7. Suggested 6-hour plan (not mandatory)

- **H0–0:45** — Load & profile the catalog. Build normalizers for price/stock and a
  searchable index (text + OEM + vehicle). Look at how dirty the data really is.
- **H0:45–2:00** — Core matcher: LLM-based semantic match over candidate SKUs
  (retrieve candidates cheaply, then let the model rank + decide). Output the structured
  schema for one order end-to-end.
- **H2:00–3:30** — The ask-vs-assume decision layer + confidence calibration. Run all 15,
  compare to your own expectations.
- **H3:30–4:30** — Image path (vision step → part identity → match) + customer-reply
  drafting in Spanish.
- **H4:30–5:00** — Polish the demo runner (`python run.py order_XX.txt`).
- **H5:00–5:45** — Inject & implement the surprise requirement (margins + auto-alternative).
- **H5:45–6:00** — Dry-run the live demo with 2–3 brand-new orders you write yourself.

## 8. Tech notes (you have full freedom)

- Any language/stack. An LLM with tool/function calling + a lightweight retrieval step
  over the catalog is a natural fit, but a well-tuned embedding search + reranker is
  equally valid.
- Keep a **candidate-retrieval → LLM-rank-and-decide** split so you're not stuffing 874
  rows into every prompt; it's cheaper and more accurate.
- Log every decision. The reasoning trail is half your score.
- A tiny CLI is enough for the demo — no UI required. Optional: a 1-screen web view that
  shows the structured order + reply side by side scores well on "viability" with little
  effort.

---

**Deliverable:** a repo that, given any `order_XX.txt` (including ones the judge writes on
the spot), prints the structured order, the quote, and a Spanish customer-reply draft —
and, after the hour-5 change, the margin and auto-suggested alternatives.

Now go give it everything. 🔥
