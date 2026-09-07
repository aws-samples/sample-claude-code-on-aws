---
name: claim-triage
description: Triage an insurance claim by gathering data, assessing severity, and producing a structured report.
version: 1.0.0
---

Triage an insurance claim by gathering data from available tools, assessing severity, and producing a structured triage report.

Arguments: $ARGUMENTS

## Triage Process

### Step 1 — Identify the Claim
Parse the input to extract a claim ID (e.g., CLM-2025-0067) or policyholder name.
If the input is ambiguous, ask for clarification before proceeding.

### Step 2 — Gather Claim Details
Use the `ClaimsData___query_claims` tool to retrieve the full claim record.
Note the claim type, status, amount claimed, and any adjuster notes.

### Step 3 — Retrieve Policy Context
Extract the policy number from the claim record and use `PolicyLookup___lookup_policy`
to retrieve the associated policy. Note coverage limits, policy status, and expiry date.

### Step 4 — Assess Severity
Classify the claim into one of these severity tiers based on the data gathered:

| Tier | Criteria | SLA |
|------|----------|-----|
| **P1 — Critical** | Amount > $150K, OR status contains "LEGAL HOLD", OR policy expired/under review | 4 hours |
| **P2 — High** | Amount > $50K, OR status "Under Investigation", OR multiple claims on same policy | 24 hours |
| **P3 — Standard** | Amount $10K–$50K with no complicating factors | 3 business days |
| **P4 — Low** | Amount < $10K, straightforward claim with clear liability | 5 business days |

### Step 5 — Check for Red Flags
Flag any of the following if present:
- Claim amount exceeds policy coverage limits
- Multiple open claims from the same policyholder
- Claim filed within 90 days of policy inception
- "Under Investigation" or "LEGAL HOLD" in adjuster notes
- Policy status is not "Active"

### Step 6 — Produce Triage Report
Output a structured report in this exact format:

```
=== CLAIM TRIAGE REPORT ===
Claim ID:       [claim_id]
Policyholder:   [name]
Policy:         [policy_number] ([type], [status])
Claim Type:     [type]
Amount Claimed: [amount]
Coverage Limit: [relevant coverage from policy]

SEVERITY:       [P1/P2/P3/P4] — [tier name]
SLA:            [response time]

RED FLAGS:
- [list any flags, or "None identified"]

RECOMMENDED ACTIONS:
1. [First action based on severity and flags]
2. [Second action]
3. [Third action if applicable]

NOTES:
[Any additional context from adjuster notes or policy review]
===========================
```

If the AgentCore Gateway tools are not available, inform the user that this skill
requires the PolicyLookup and ClaimsData tools, and suggest connecting to the Gateway first.
