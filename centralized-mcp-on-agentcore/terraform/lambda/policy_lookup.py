import json

POLICY_DATA = {
    "POL-10042": {
        "policy_number": "POL-10042",
        "holder": "Sarah Chen",
        "type": "Auto Insurance",
        "status": "Active",
        "coverage": "$500K liability, $100K collision",
        "premium_monthly": "$185",
        "effective_date": "2025-06-01",
        "expiry_date": "2026-06-01",
        "vehicle": "2023 Toyota RAV4",
    },
    "POL-10078": {
        "policy_number": "POL-10078",
        "holder": "James Rodriguez",
        "type": "Home Insurance",
        "status": "Active",
        "coverage": "$750K dwelling, $300K personal property",
        "premium_monthly": "$220",
        "effective_date": "2025-03-15",
        "expiry_date": "2026-03-15",
        "property": "123 Example Street, Sampleville NSW 2000",
    },
    "POL-10103": {
        "policy_number": "POL-10103",
        "holder": "Emily Watson",
        "type": "Life Insurance",
        "status": "Active",
        "coverage": "$1M term life, 20-year term",
        "premium_monthly": "$95",
        "effective_date": "2024-11-01",
        "expiry_date": "2044-11-01",
        "beneficiary": "Michael Watson (spouse)",
    },
    "POL-10156": {
        "policy_number": "POL-10156",
        "holder": "David Park",
        "type": "Business Insurance",
        "status": "Under Review",
        "coverage": "$2M general liability, $500K property",
        "premium_monthly": "$410",
        "effective_date": "2025-09-01",
        "expiry_date": "2026-09-01",
        "business": "Park's Auto Repair Pty Ltd",
    },
    "POL-10201": {
        "policy_number": "POL-10201",
        "holder": "Maria Gonzalez",
        "type": "Health Insurance",
        "status": "Active",
        "coverage": "Gold Hospital + Extras",
        "premium_monthly": "$310",
        "effective_date": "2025-01-01",
        "expiry_date": "2026-01-01",
        "members": "Family (4 members)",
    },
}


def lambda_handler(event, context):
    policy_number = event.get("policy_number", "").upper().strip()
    if policy_number in POLICY_DATA:
        return {"statusCode": 200, "body": json.dumps(POLICY_DATA[policy_number])}
    available = list(POLICY_DATA.keys())
    return {"statusCode": 200, "body": json.dumps({
        "error": f"Policy '{policy_number}' not found. Available policies: {available}"
    })}
