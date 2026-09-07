import json
import os

# --- Claims Data ---
# Amounts stored as numbers for filtering; formatted as currency in responses.
# Includes high-value claims (>$100K) for Cedar contextual control demos.
CLAIMS_DATA = {
    "CLM-2024-0891": {
        "claim_id": "CLM-2024-0891",
        "policy_number": "POL-10042",
        "holder": "Sarah Chen",
        "type": "Auto - Collision",
        "status": "Approved",
        "amount_claimed": 12400,
        "amount_approved": 11800,
        "date_filed": "2025-12-15",
        "date_resolved": "2026-01-20",
        "adjuster_notes": "Rear-end collision on Pacific Hwy. Liability confirmed via dashcam footage. Deductible of $600 applied.",
        "classification": "CONFIDENTIAL",
    },
    "CLM-2025-0023": {
        "claim_id": "CLM-2025-0023",
        "policy_number": "POL-10078",
        "holder": "James Rodriguez",
        "type": "Home - Storm Damage",
        "status": "In Progress",
        "amount_claimed": 45000,
        "amount_approved": None,
        "date_filed": "2026-02-28",
        "date_resolved": None,
        "adjuster_notes": "Severe storm damage to roof and north-facing windows. Structural engineer assessment scheduled. Temporary accommodation approved under policy.",
        "classification": "CONFIDENTIAL",
    },
    "CLM-2025-0067": {
        "claim_id": "CLM-2025-0067",
        "policy_number": "POL-10156",
        "holder": "David Park",
        "type": "Business - Property Damage",
        "status": "Under Investigation",
        "amount_claimed": 89500,
        "amount_approved": None,
        "date_filed": "2026-03-10",
        "date_resolved": None,
        "adjuster_notes": "Fire damage to workshop. Cause under investigation - electrical fault suspected. Forensic report pending. High-value claim flagged for senior adjuster review.",
        "classification": "CONFIDENTIAL - UNDER INVESTIGATION",
    },
    "CLM-2025-0112": {
        "claim_id": "CLM-2025-0112",
        "policy_number": "POL-10078",
        "holder": "James Rodriguez",
        "type": "Home - Water Damage",
        "status": "In Progress",
        "amount_claimed": 185000,
        "amount_approved": None,
        "date_filed": "2026-03-25",
        "date_resolved": None,
        "adjuster_notes": "Major pipe burst caused flooding across two floors. Structural assessment and mold remediation required. High-value claim flagged for senior review.",
        "classification": "CONFIDENTIAL - HIGH VALUE",
    },
    "CLM-2025-0134": {
        "claim_id": "CLM-2025-0134",
        "policy_number": "POL-10156",
        "holder": "David Park",
        "type": "Business - Liability",
        "status": "Under Review",
        "amount_claimed": 250000,
        "amount_approved": None,
        "date_filed": "2026-04-01",
        "date_resolved": None,
        "adjuster_notes": "Third-party liability claim following customer injury on premises. Legal review in progress. Exceeds standard authority limit.",
        "classification": "CONFIDENTIAL - LEGAL HOLD",
    },
}

QUARTERLY_SUMMARY = {
    "period": "Q1 2026",
    "total_claims_filed": 147,
    "total_claims_resolved": 112,
    "total_amount_paid": "$2.3M",
    "avg_resolution_days": 18,
    "top_category": "Auto - Collision (42%)",
    "fraud_flagged": 3,
    "classification": "CONFIDENTIAL - INTERNAL USE ONLY",
}

# --- Approach 2: Per-user claim amount limits (Lambda-side filtering) ---
# Configured via environment variables (set in Terraform / Lambda config):
#   CONTEXTUAL_USER: Okta user email (JWT sub) with a claim amount limit
#   CONTEXTUAL_MAX_AMOUNT: Maximum claim amount visible to that user (default: 100000)
# Users not configured have no limit (full access).
_contextual_user = os.environ.get("CONTEXTUAL_USER", "")
_contextual_max_amount = int(os.environ.get("CONTEXTUAL_MAX_AMOUNT", "100000"))
USER_CLAIM_LIMITS = {_contextual_user: _contextual_max_amount} if _contextual_user else {}


def _format_amount(val):
    """Format numeric amount as currency string for display."""
    if val is None:
        return "Pending"
    return f"${val:,.0f}"


def _format_claim(claim):
    """Return a display-friendly copy of a claim with formatted amounts."""
    out = dict(claim)
    out["amount_claimed"] = _format_amount(claim["amount_claimed"])
    out["amount_approved"] = _format_amount(claim.get("amount_approved"))
    return out


def _filter_by_amount(claims, max_amount):
    """Return only claims where amount_claimed <= max_amount."""
    return {k: v for k, v in claims.items() if v["amount_claimed"] <= max_amount}


def lambda_handler(event, context):
    query = event.get("query", "").lower().strip()
    max_amount = event.get("max_amount")  # Approach 1: Cedar-enforced input constraint

    # --- Approach 2: Lambda-side filtering based on caller identity ---
    # AgentCore Gateway passes the authenticated principal in requestContext.
    # If present, apply per-user claim limits defined in USER_CLAIM_LIMITS.
    caller_id = None
    request_ctx = event.get("requestContext", {})
    if isinstance(request_ctx, dict):
        caller_id = request_ctx.get("principalId") or request_ctx.get("sub")
    if caller_id and caller_id in USER_CLAIM_LIMITS and max_amount is None:
        max_amount = USER_CLAIM_LIMITS[caller_id]

    # Apply amount filter if set (from Cedar input constraint OR Lambda-side limit)
    working_claims = CLAIMS_DATA
    if max_amount is not None:
        try:
            max_amount = int(max_amount)
        except (ValueError, TypeError):
            return {"statusCode": 400, "body": json.dumps({
                "error": f"max_amount must be a number, got: {max_amount}"
            })}
        working_claims = _filter_by_amount(CLAIMS_DATA, max_amount)

    # Summary / aggregate queries
    if "summary" in query or "quarterly" in query or "all" in query or "overview" in query:
        return {"statusCode": 200, "body": json.dumps({
            "claims": [_format_claim(c) for c in working_claims.values()],
            "quarterly_summary": QUARTERLY_SUMMARY,
            "filter_applied": f"max_amount <= ${max_amount:,}" if max_amount else "none",
        })}

    # Specific claim lookup
    for claim_id, data in working_claims.items():
        if claim_id.lower() in query:
            return {"statusCode": 200, "body": json.dumps(_format_claim(data))}

    # Search by policy number
    for claim_id, data in working_claims.items():
        if data["policy_number"].lower() in query:
            return {"statusCode": 200, "body": json.dumps(_format_claim(data))}

    # Search by holder name
    for claim_id, data in working_claims.items():
        if data["holder"].lower() in query:
            return {"statusCode": 200, "body": json.dumps(_format_claim(data))}

    return {"statusCode": 200, "body": json.dumps({
        "available_claims": list(working_claims.keys()),
        "hint": "Query by claim ID, policy number, holder name, or ask for 'claims summary'",
        "filter_applied": f"max_amount <= ${max_amount:,}" if max_amount else "none",
    })}
