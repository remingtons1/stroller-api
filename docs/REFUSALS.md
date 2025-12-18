# Refusals & Disclosures (demo)

This service is designed to be a **truth/disclosure layer**, not a recommender.

## Hard refusals

- **Air travel / overhead bin:**
  - We do **not** claim a stroller fits airline overhead bins unless `fold_characteristics` includes `cabin_approved`.

## Disclosures (always allowed, often required)

- Missing/low confidence on core comparison fields (`stroller_weight_lb`, `folded_dimensions_in`, `max_child_weight_lb`)
- Region mismatch fields (e.g., EU spec used for US product) are disclosed and excluded from ranking/comparisons
- Configuration scope notes (e.g., weight excludes accessories / seat / canopy) are surfaced as scope disclosures

## Non-goals

- No rankings
- No “best stroller” outputs
- No claims not supported by verified specs
