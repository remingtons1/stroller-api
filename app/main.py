from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

from fastapi import FastAPI
from pydantic import BaseModel, Field

# Support both local dev (../data) and Docker (/app/data)
_APP_DIR = Path(__file__).resolve().parent
_DATA_DIR = Path(os.environ.get("DATA_DIR", _APP_DIR.parent / "data"))
DATA_PATH = _DATA_DIR / "strollers.json"


class Constraints(BaseModel):
    terrain: Optional[Literal["smooth", "urban", "light_uneven", "all_terrain", "jogging"]] = None
    max_weight_lbs: Optional[float] = Field(default=None, description="Max stroller weight (lb) user will accept.")
    travel: Optional[Literal["air", "none"]] = Field(default=None, description="If 'air', apply carry-on/refusal logic.")


class EligibleProductsRequest(BaseModel):
    region: Literal["US"] = "US"
    constraints: Constraints = Field(default_factory=Constraints)


class Disclosure(BaseModel):
    type: Literal["missing_data", "low_confidence", "region_mismatch", "scope_mismatch"]
    message: str
    fields: List[str] = Field(default_factory=list)


class EligibilityStatus(BaseModel):
    status: Literal["eligible", "ineligible", "needs_review"]
    reasons: List[str] = Field(default_factory=list)


class ProductResult(BaseModel):
    product_id: str
    brand: str
    model: str
    variant: Optional[str] = None
    intended_use_category: Optional[str] = None
    eligibility: EligibilityStatus
    required_disclosures: List[Disclosure] = Field(default_factory=list)
    refusals: List[str] = Field(default_factory=list)
    highlights: Dict[str, Any] = Field(default_factory=dict)


class EligibleProductsResponse(BaseModel):
    region: str
    constraints: Dict[str, Any]
    eligible_products: List[ProductResult] = Field(default_factory=list)
    ineligible_products: List[ProductResult] = Field(default_factory=list)
    needs_review_products: List[ProductResult] = Field(default_factory=list)
    meta: Dict[str, Any] = Field(default_factory=dict)


def _load_dataset() -> Dict[str, Any]:
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _conf_rank(conf: Optional[str]) -> int:
    if conf == "high":
        return 3
    if conf == "medium":
        return 2
    if conf == "low":
        return 1
    return 0


def _field_value(stroller: Dict[str, Any], field: str) -> Tuple[Any, Optional[str], bool]:
    obj = stroller.get(field)
    if not isinstance(obj, dict):
        return obj, None, False
    excluded = bool(obj.get("excluded_from_recommendations", False))
    return obj.get("value", obj), obj.get("confidence"), excluded


def _get_str_field(stroller: Dict[str, Any], field: str, default: str = "") -> str:
    """Extract string value from field that might be a plain string or a dict with 'value' key."""
    val = stroller.get(field)
    if val is None:
        return default
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        return val.get("value") or default
    return default


def _has_low_conf_core(stroller: Dict[str, Any]) -> List[str]:
    low_fields: List[str] = []
    for f in ["stroller_weight_lb", "folded_dimensions_in", "max_child_weight_lb"]:
        if f == "folded_dimensions_in":
            obj = stroller.get(f) or {}
            conf = obj.get("confidence")
            v = obj if obj else None
            if v is None or _conf_rank(conf) < 2:
                low_fields.append(f)
            continue
        v, conf, excluded = _field_value(stroller, f)
        if v is None or _conf_rank(conf) < 2 or excluded:
            low_fields.append(f)
    return low_fields


def _terrain_ok(stroller: Dict[str, Any], required: str) -> Tuple[bool, str]:
    tags_obj = stroller.get("terrain_tags") or {}
    tags = tags_obj.get("value") or []
    if required in tags:
        return True, ""
    if required == "jogging" and _get_str_field(stroller, "intended_use_category") == "jogging":
        return True, ""
    return False, f"terrain_not_matched:{required}"


def _air_travel_refusals(stroller: Dict[str, Any]) -> List[str]:
    fc = stroller.get("fold_characteristics") or {}
    chars = fc.get("value") or []
    if "cabin_approved" in chars:
        return []
    return ["air_travel:cannot_claim_overhead_bin_fit_without_cabin_approved_verification"]


def _highlights(stroller: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    w = (stroller.get("stroller_weight_lb") or {}).get("value")
    if w is not None:
        out["stroller_weight_lb"] = w
    fd = stroller.get("folded_dimensions_in")
    if isinstance(fd, dict) and all(k in fd for k in ["length", "width", "height"]):
        out["folded_dimensions_in"] = {"length": fd["length"], "width": fd["width"], "height": fd["height"]}
    mcw = (stroller.get("max_child_weight_lb") or {}).get("value")
    if mcw is not None:
        out["max_child_weight_lb"] = mcw
    out["seat_reversible"] = bool((stroller.get("seat_reversible") or {}).get("value", False))
    out["travel_system_compatibility"] = (stroller.get("travel_system_compatibility") or {}).get("value")
    return out


def _disclosures(stroller: Dict[str, Any]) -> List[Disclosure]:
    disclosures: List[Disclosure] = []

    prov = stroller.get("provenance_summary") or {}
    if prov.get("has_region_mismatch"):
        disclosures.append(
            Disclosure(
                type="region_mismatch",
                message=(
                    "Some fields were sourced from a different region and are excluded from ranking/comparisons."
                ),
                fields=list(prov.get("mismatched_fields") or []),
            )
        )

    low_core = _has_low_conf_core(stroller)
    if low_core:
        disclosures.append(
            Disclosure(
                type="low_confidence",
                message=(
                    "One or more core comparison fields are missing/low confidence/excluded; product may require manual verification."
                ),
                fields=low_core,
            )
        )

    scope = _get_str_field(stroller, "configuration_scope")
    if "excludes" in scope or "separate" in scope:
        disclosures.append(
            Disclosure(
                type="scope_mismatch",
                message=(
                    "Weight/sizing may be for a specific configuration (e.g., seat-only, excludes accessories). Check scope notes before comparing."
                ),
                fields=["configuration_scope"],
            )
        )

    return disclosures


def evaluate(stroller: Dict[str, Any], constraints: Constraints) -> ProductResult:
    reasons: List[str] = []
    refusals: List[str] = []
    disclosures = _disclosures(stroller)

    if constraints.terrain:
        ok, reason = _terrain_ok(stroller, constraints.terrain)
        if not ok:
            reasons.append(reason)

    if constraints.max_weight_lbs is not None:
        w = (stroller.get("stroller_weight_lb") or {}).get("value")
        w_conf = (stroller.get("stroller_weight_lb") or {}).get("confidence")
        if w is None or _conf_rank(w_conf) < 2:
            reasons.append("weight_unverified_for_comparison")
        elif w > float(constraints.max_weight_lbs):
            reasons.append(f"over_weight_limit:{w}>{constraints.max_weight_lbs}")

    if constraints.travel == "air":
        refusals.extend(_air_travel_refusals(stroller))

    if reasons:
        status: Literal["eligible", "ineligible", "needs_review"] = "ineligible"
    else:
        status = "needs_review" if _has_low_conf_core(stroller) else "eligible"

    # Extract string fields safely - they might be plain strings or dicts with 'value' key
    variant_val = _get_str_field(stroller, "variant")

    return ProductResult(
        product_id=stroller["product_id"],
        brand=_get_str_field(stroller, "brand"),
        model=_get_str_field(stroller, "model"),
        variant=variant_val if variant_val else None,
        intended_use_category=_get_str_field(stroller, "intended_use_category") or None,
        eligibility=EligibilityStatus(status=status, reasons=reasons),
        required_disclosures=disclosures,
        refusals=refusals,
        highlights=_highlights(stroller),
    )


app = FastAPI(
    title="Stroller Truth API",
    version="0.1.0",
    description=(
        "A trust-scored stroller spec API. Returns eligibility, refusals, and disclosures — not rankings. "
        "Every field carries provenance (source URL + confidence). Low-confidence and region-mismatched "
        "data is disclosed but excluded from comparisons."
    ),
)


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/datasets/strollers")
def list_strollers(
    region: Optional[str] = None,
    intended_use_category: Optional[str] = None,
    seat_reversible: Optional[bool] = None,
    confidence_min: Optional[Literal["high", "medium", "low"]] = None,
) -> Dict[str, Any]:
    """List strollers with optional filters."""
    dataset = _load_dataset()
    strollers = dataset.get("strollers") or []
    
    results = []
    for s in strollers:
        # Apply filters
        if region and s.get("region") != region:
            continue
        if intended_use_category and _get_str_field(s, "intended_use_category") != intended_use_category:
            continue
        if seat_reversible is not None:
            sr = (s.get("seat_reversible") or {}).get("value")
            if sr != seat_reversible:
                continue
        if confidence_min:
            min_rank = _conf_rank(confidence_min)
            low_fields = _has_low_conf_core(s)
            if low_fields and min_rank >= 2:
                continue
        
        results.append({
            "product_id": s["product_id"],
            "brand": _get_str_field(s, "brand"),
            "model": _get_str_field(s, "model"),
            "variant": _get_str_field(s, "variant") or None,
            "region": s.get("region"),
            "intended_use_category": _get_str_field(s, "intended_use_category") or None,
            "highlights": _highlights(s),
            "required_disclosures": [d.model_dump() for d in _disclosures(s)],
        })
    
    return {
        "count": len(results),
        "strollers": results,
        "meta": {
            "dataset_extracted_date": dataset.get("extracted_date"),
            "schema_version": (dataset.get("schema") or {}).get("version"),
        }
    }


@app.get("/v1/strollers/{product_id}")
def get_stroller(product_id: str) -> Dict[str, Any]:
    """Get a single stroller by product_id."""
    dataset = _load_dataset()
    for s in dataset.get("strollers") or []:
        if s["product_id"] == product_id:
            return {
                "stroller": s,
                "required_disclosures": [d.model_dump() for d in _disclosures(s)],
            }
    return {"error": "not_found", "product_id": product_id}


@app.post("/v1/eligible-products", response_model=EligibleProductsResponse)
def eligible_products(req: EligibleProductsRequest) -> EligibleProductsResponse:
    """Filter products by constraints, returning eligibility status, disclosures, and refusals."""
    dataset = _load_dataset()
    strollers: List[Dict[str, Any]] = dataset.get("strollers") or []

    eligible: List[ProductResult] = []
    ineligible: List[ProductResult] = []
    needs_review: List[ProductResult] = []

    for s in strollers:
        if (s.get("region") or "US") != req.region:
            continue

        result = evaluate(s, req.constraints)
        if result.eligibility.status == "eligible":
            eligible.append(result)
        elif result.eligibility.status == "needs_review":
            needs_review.append(result)
        else:
            ineligible.append(result)

    return EligibleProductsResponse(
        region=req.region,
        constraints=req.constraints.model_dump(exclude_none=True),
        eligible_products=eligible,
        ineligible_products=ineligible,
        needs_review_products=needs_review,
        meta={
            "dataset_extracted_date": dataset.get("extracted_date"),
            "schema_version": (dataset.get("schema") or {}).get("version"),
            "count_total": len(strollers),
            "count_eligible": len(eligible),
            "count_needs_review": len(needs_review),
            "count_ineligible": len(ineligible),
        },
    )