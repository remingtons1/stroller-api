# Stroller Specs API — Developer Spec

## What You're Building

A **trust-scored stroller comparison API** that returns eligibility, disclosures, and refusals — not rankings or recommendations.

**Core principle:** Every spec field carries provenance (source URL + confidence level). Low-confidence or region-mismatched data is disclosed but excluded from comparisons.

---

## Endpoints (MVP)

### 1. `POST /v1/datasets/strollers`
Ingest a dataset snapshot. Validate against JSON Schema, store stroller records with field-level provenance.

**Acceptance criteria:**
- [ ] Rejects payloads that fail schema validation (return 400 + specific errors)
- [ ] Stores `extracted_date` and `schema.version` as metadata
- [ ] Handles upserts by `product_id` (idempotent)

### 2. `GET /v1/datasets/strollers`
List/filter strollers.

**Query params:** `region`, `intended_use_category`, `seat_reversible`, `confidence_min`

**Acceptance criteria:**
- [ ] `confidence_min=medium` excludes products where core fields are low-confidence
- [ ] Returns highlights (weight, folded dims, max child weight) in response
- [ ] Includes `required_disclosures` array per product

### 3. `POST /v1/compare`
Compare 2–6 strollers apples-to-apples.

**Request body:**
```json
{
  "product_ids": ["uppababy_cruz_v2_us", "babyzen_yoyo2_us"],
  "region": "US",
  "fields": ["stroller_weight_lb", "folded_dimensions_in"]
}
```

**Acceptance criteria:**
- [ ] Emits `warnings` when a field is excluded from comparison (low confidence, region mismatch)
- [ ] Returns comparison matrix with provenance per cell
- [ ] Does NOT rank or declare a "winner"

### 4. `POST /v1/eligible-products` ✅ (included in demo)
Filter products by constraints (terrain, max weight, travel type).

**Acceptance criteria:**
- [x] Returns `eligible`, `ineligible`, `needs_review` buckets
- [x] Air travel constraint triggers refusal if `cabin_approved` not verified
- [x] Surfaces all required disclosures

---

## Data Rules (Non-Negotiable)

| Rule | Implementation |
|------|----------------|
| **Confidence gate** | Only `high` or `medium` confidence fields can influence comparisons/rankings |
| **Low confidence** | Display only — always disclosed to user |
| **Region mismatch** | Never influences ranking; disclosed and excluded |
| **Air travel claims** | Refuse "fits overhead bin" unless `fold_characteristics` includes `cabin_approved` |
| **Scope notes** | Surface `configuration_scope` when weight/dims might vary by config |

---

## Core Fields for Ranking

These fields must be `high` or `medium` confidence to participate in comparisons:

- `stroller_weight_lb`
- `folded_dimensions_in` (length × width × height)
- `max_child_weight_lb`

---

## Confidence Rubric

| Level | Definition |
|-------|------------|
| `high` | Manufacturer spec page or official manual PDF |
| `medium` | Reputable retailer or consistent third-party sources |
| `low` | Blogs, reviews, EU sources for US products, conflicting data |

---

## File Structure

```
├── app/
│   └── main.py              # FastAPI demo (working)
├── data/
│   └── strollers.json       # 19-product dataset
├── schemas/
│   └── stroller-dataset-0.4.0.schema.json
├── docs/
│   ├── DEVELOPER_SPEC.md    # This file
│   ├── REFUSALS.md          # Refusal/disclosure philosophy
│   └── openapi.yaml         # Full API contract
├── postman/
│   └── Stroller-Specs.postman_collection.json
├── Dockerfile
├── requirements.txt
└── README.md
```

---

## Quick Start

```bash
# With Docker
docker build -t stroller-api .
docker run -p 8000:8000 stroller-api

# Or locally
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

```bash
# Health check
curl http://localhost:8000/health

# List all US strollers
curl "http://localhost:8000/v1/datasets/strollers?region=US"

# Query eligible products under 25 lbs
curl -X POST http://localhost:8000/v1/eligible-products \
  -H "Content-Type: application/json" \
  -d '{"region": "US", "constraints": {"max_weight_lbs": 25}}'
```

---

## What's NOT in Scope

- No rankings or "best stroller" outputs
- No price data
- No user reviews or ratings
- No claims not supported by verified specs

---

## Questions?

The demo at `app/main.py` is a working reference implementation. The `/v1/eligible-products` endpoint demonstrates the full eligibility/disclosure/refusal pattern you'll extend to the other endpoints.
