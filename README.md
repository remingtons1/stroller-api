# Stroller Specs API

A trust-scored stroller comparison API with field-level provenance.

## The Idea

An "apples-to-apples" stroller comparison engine where every spec is **normalized, region-aware, and trust-scored** — so rankings don't get polluted by bad or mismatched data.

## What Makes This Different

- **Field-level provenance:** Every value has `source_url` + `confidence` (high/medium/low)
- **Confidence gating:** Only high/medium confidence data influences comparisons
- **Region mismatch handling:** EU specs for US products are disclosed and excluded
- **Explicit refusals:** Won't claim "fits overhead bin" without verification

## Quick Start

```bash
# Docker (recommended)
docker build -t stroller-api .
docker run -p 8000:8000 stroller-api

# Or locally
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Test It

```bash
# Health check
curl http://localhost:8000/health

# List strollers
curl "http://localhost:8000/v1/datasets/strollers?region=US&confidence_min=medium"

# Find lightweight strollers under 25 lbs
curl -X POST http://localhost:8000/v1/eligible-products \
  -H "Content-Type: application/json" \
  -d '{"region": "US", "constraints": {"max_weight_lbs": 25}}'

# Find jogging strollers
curl -X POST http://localhost:8000/v1/eligible-products \
  -H "Content-Type: application/json" \
  -d '{"region": "US", "constraints": {"terrain": "jogging"}}'
```

## Project Structure

```
├── app/main.py                    # FastAPI service (working demo)
├── data/strollers.json            # 19-product dataset
├── schemas/                       # JSON Schema for validation
├── docs/
│   ├── DEVELOPER_SPEC.md          # ⭐ Start here — full build spec
│   ├── REFUSALS.md                # Refusal/disclosure philosophy
│   └── openapi.yaml               # API contract
├── postman/                       # Ready-to-import Postman collection
├── Dockerfile
└── requirements.txt
```

## What to Build

See **[docs/DEVELOPER_SPEC.md](docs/DEVELOPER_SPEC.md)** for:
- Endpoint specifications with acceptance criteria
- Data rules (confidence gating, region mismatch handling)
- What's in scope vs. out of scope

## Dataset

19 strollers with full provenance:
- UPPAbaby Cruz V2, Vista V2
- BOB Alterrain Pro, Revolution Flex 3.0
- Baby Jogger Summit X3, City Mini GT2, City Select 2
- Bugaboo Fox 5, Butterfly
- Nuna MIXX Next, TRVL, DEMI Next
- Babyzen YOYO2
- Thule Urban Glide 2
- Chicco Bravo Trio
- Ergobaby Metro+
- Mockingbird Single-to-Double
- Cybex Gazelle S

## API Docs

Once running, visit: http://localhost:8000/docs
