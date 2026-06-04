# Order Translator — RepuExpress

An AI agent that turns a **messy natural-language parts order** (Spanish/Spanglish,
typos, slang, sometimes a photo) into a **structured, quote-ready order with a
drafted customer reply** — handling ambiguity the way a sharp salesperson would,
not the way a rigid web form does.

```bash
python run.py order_03.txt
```
```jsonc
{
  "order_id": "order_03",
  "channel": "email",
  "line_items": [
    { "customer_text": "pastillas de freno", "matched_sku": "SKU-1010",
      "matched_name": "Pastillas de Freno Renault Duster 2016", "quantity": 1,
      "unit_price": 68000, "line_total": 68000, "confidence": 0.93,
      "decision": "auto_matched", "reasoning": "...",
      "unit_cost": 47600, "line_margin": 20400 },
    { "customer_text": "un par de amortiguadores", "matched_sku": null,
      "quantity": 2, "confidence": 0.40, "decision": "needs_clarification",
      "clarifying_question": "¿Los amortiguadores son delanteros o traseros?" }
  ],
  "questions_for_customer": ["¿Los amortiguadores son delanteros o traseros?"],
  "customer_reply_draft": "Hola, ya te cotizo las pastillas ($68.000). Para los amortiguadores, ¿los necesitás delanteros o traseros?",
  "quote_total_partial": 68000,
  "estimated_margin_total": 20400
}
```

> Code, logs, and the output schema are in English; the *matching* survives
> Spanish input. Customer-facing text (questions, reply) is in Colombian Spanish.

---

## The problem

RepuExpress is a Colombian auto & motorcycle parts distributor. Orders arrive via
WhatsApp, email, and a web form as disorganized text, matched against a
deliberately **messy 874-SKU catalog** (mixed ES/EN names, blank fields, prices in
~15 formats, duplicates, supersessions). The hard part is **not** parsing clean
input. It's:

1. **Fuzzy, cross-language semantic matching** — the customer's words almost never
   match the catalog text literally (`balineras` ≈ `wheel bearing`).
2. **The ask-vs-assume decision** — an agent that asks about everything is useless;
   one that assumes everything quotes wrong. Walking that line, and **justifying
   every call**, is the heart of the problem.

---

## How it works

A **deterministic pipeline** orchestrates the flow; the **LLM reasons only at
specific nodes** (extract, decide, reply). Code handles the deterministic parts
(parsing, retrieval, normalization, quoting, margin).

```
order_XX.txt
   │
   ▼  [1] ingest        parse header + message; the photo (order 07) is routed as
   │   (src/ingest.py)  an attachment carrying "vision_text" (simulated vision output)
   ▼
   │  [2] extract  🧠   messy message → a list of structured "intents"
   │   (src/extract.py) (validated structured output: part, vehicle, qty, OEM…)
   ▼
   │  [3] retrieve       each intent → top-K candidate SKUs
   │   (src/retriever.py · src/decide.gather_candidates)
   │     ├─ semantic: model2vec embeddings + cosine similarity (offline)
   │     └─ exact: OEM-code lookup (by_oem) — orders 07/13
   ▼
   │  [4] decide   🧠   pick the SKU ONLY from the candidates, or ask
   │   (src/decide.py)  → auto_matched | needs_clarification | not_found
   │     · loop capped at 2 questions (specific name → show catalog options)
   │     · anti-hallucination guard: matched_sku must be in the candidate set
   ▼
   │  [5] quote          normalized price × qty; estimated margin (hour-5)
   │   (src/quote.py · src/margin.py)
   │     · out of stock → auto-suggested in-stock alternative (same category + vehicle)
   ▼
   │  [6] reply    🧠   natural Colombian-Spanish customer reply draft
   │   (src/reply.py)
   ▼
StructuredOrder (JSON)   — assembled by src/pipeline.py
```

🧠 = LLM (Claude) step. Everything else is deterministic code, tested offline.

---

## Design decisions (the *why*)

### 1. Hybrid orchestrated architecture (not a free autonomous agent)
The flow is a **fixed-stage pipeline**; the LLM decides at specific nodes. A free
agentic loop is unpredictable in a live demo, hard to debug, and can't guarantee a
**uniform reasoning trail** — and that trail is ~half the score. The pipeline gives
predictability and a clean trace while keeping the LLM's judgment exactly where
matching needs it. This is what the challenge suggests:
`candidate-retrieval → LLM-rank-and-decide`.

### 2. RAG with embeddings for candidate retrieval
The matching node never receives all 874 rows in the prompt: a **retrieval** step
indexes the catalog as vectors (offline) and fetches the ~K nearest SKUs *by
meaning*. The LLM then reasons over a handful of real candidates (it can't
hallucinate a SKU), it's cheap, and it bridges the Spanish↔English gap. The cost:
final quality is capped by retrieval recall → so K isn't tiny, and exact OEM lookup
complements it.

### 3. Local static embeddings via `model2vec` (no torch, no API)
No embeddings API is available (only `ANTHROPIC_API_KEY`, and Anthropic doesn't do
embeddings), and the environment is Python 3.14 with no system `pip`. We chose
**`model2vec`** (a multilingual *potion* model — static `token→vector` embeddings +
mean-pool): runs on numpy alone, **no torch** (a minefield on 3.14), a single
download (~100-300 MB) and then fully offline, embeds all 874 rows in <1 s. We give
up some semantic ceiling (very regional slang can miss) for zero friction and
speed — the LLM's judgment compensates.

### 4. Catalog as an index-aligned list + dict indexes (no pandas)
At 874 rows efficiency isn't the deciding factor; **access pattern** is. The catalog
loads as a `list[CatalogItem]` **index-aligned with the embedding matrix**
(`items[i] ↔ embeddings[i]`), so the similarity `argsort` returns indices that map
straight to items. On top: `by_sku` (supersession) and `by_oem` (exact, one-to-many
because of duplicates). Each `CatalogItem` keeps **raw + normalized** values so every
decision can be audited.

### 5. Deterministic normalizers (price, stock, OEM)
Prices arrive in ~15 formats (`$238.400`, `15429.00`, `COP 67091`): a dot followed by
exactly 2 digits is cents (dropped), any other dot is a thousands separator. Stock
mixes integers with `agotado`/`few`/blank → typed to `(quantity, status)`. OEM is
reduced to a comparable key (uppercase, no `OEM`/dashes), which makes orders 07/13 a
trivial O(1) lookup.

### 6. Extract via structured outputs (the LLM only structures)
The message becomes a validated list of intents via `messages.parse()` + a Pydantic
schema — the JSON always comes back well-shaped, no prose parsing. Extract **only
structures**: it does not match SKUs or decide. The photo enters as one more intent
through the attachment's `vision_text`.

### 7. Ask-vs-assume loop (max 2 questions + guard)
The LLM picks the SKU **only from the candidate shortlist** and returns a structured
`Decision` (`auto_matched | needs_clarification | not_found`). When unsure, an
autonomous loop asks **at most twice, escalating precision**: 1) do you have the
specific part name?; 2) here are the catalog options — which fits? Then it **commits**.
It only asks when picking wrong would cost a return. A **deterministic guard** rejects
any `matched_sku` not in the candidate set → a hard guarantee against hallucinated
SKUs.

### 8. The vision step, architected for real pixels
Order 07 sends the part as a photo. The challenge's `[IMAGE DESCRIPTION ...]` block is
treated as the **simulated output of a vision step**: pulled out of the message and
parked on `Attachment.vision_text`. In a real deployment that field would be `None`
and a vision model would be called on the file — the rest of the pipeline is unchanged.

### 9. Hour-5 change (margin + alternatives)
Additive change: each line estimates **margin** (cost = 70% of price for parts, 85%
for fluids/oils; an *oil filter* is a part, not oil), and each out-of-stock SKU gets an
**auto-suggested in-stock alternative** (same category as a hard filter + same vehicle
via embedding similarity). All prior tests still pass.

---

## Project structure

```
run.py                  CLI: order_XX.txt → StructuredOrder (JSON)
src/
  models.py             CatalogItem, StockStatus, Catalog
  normalize.py          normalize_price / stock / oem
  loader.py             load_catalog → aligned list + by_sku + by_oem
  retriever.py          CatalogIndex (model2vec embeddings), retrieve, Candidate
  ingest.py             parse_order → RawOrder (+ image routing)
  extract.py            extract_intents (LLM) → LineItemIntent
  decide.py             gather_candidates, decide, resolve (LLM) + guard
  quote.py              build_line_item, quote_total, format_cop
  margin.py             is_fluid, unit_cost, suggest_alternative   (hour-5)
  reply.py              draft_reply (LLM)
  pipeline.py           process_order → StructuredOrder
tests/                  93 tests (deterministic offline; LLM ones opt-in)
info/                   CHALLENGE.md, ANSWER_KEY.md, data/ (catalog + orders)
```

---

## Tests

```bash
.venv/bin/python -m pytest tests/ -q              # offline suite (no API)
RUN_LLM_TESTS=1 .venv/bin/python -m pytest tests/ # also runs the LLM-calling tests
```

The deterministic steps (normalization, loading, retrieval, quoting, margin,
alternatives, assembly) are tested offline. The LLM steps are isolated behind
dependency injection, so the suite runs fast, free, and offline.

---

## Limitations

- **Static-retrieval ceiling:** very regional slang with little context may not land
  close. Mitigated by a wide K, exact OEM lookup, and the LLM's judgment.
- **Alternative without a category:** an out-of-stock SKU with **no** `category_hint`
  falls back to a pure semantic neighbor that can pick the wrong part type; it's
  labeled in the `reason` for human review.
- **No general lexical/fuzzy layer yet** (beyond exact OEM): the natural next
  improvement to the hybrid retrieval.

---

## Models

- **Embeddings:** `minishlab/potion-multilingual-128M`
- **LLM:** claude
