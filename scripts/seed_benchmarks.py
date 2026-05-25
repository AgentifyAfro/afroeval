"""
Seed script — generates example benchmark JSONL packs for local development.

These are NOT SME-validated. They exist to:
  - Prove the benchmark loader works.
  - Give the orchestration layer something to run against.
  - Be replaced item-by-item as SME-validated content arrives.

Run: python scripts/seed_benchmarks.py
"""

import json
from pathlib import Path

PACKS_DIR = Path(__file__).parent.parent / "benchmarks" / "packs"

SEED_PACKS = [
    {
        "filename": "mobile_money_sw_v1.0.0.jsonl",
        "items": [
            {
                "id": "mm-sw-001",
                "prompt": "Niambie jinsi ya kutuma pesa kwa M-Pesa.",
                "expected_behavior": (
                    "Eleza hatua za kutuma pesa kwa M-Pesa: "
                    "chagua 'Lipa na M-Pesa', ingiza nambari ya simu ya mpokeaji, "
                    "ingiza kiasi, thibitisha kwa PIN yako."
                ),
                "language": "sw",
                "domain": "mobile_money",
                "cohort": "informal_economy",
                "provenance": "Safaricom M-Pesa help documentation 2024",
                "is_gold": False,
                "is_held_out": False,
                "tags": ["send_money", "m-pesa", "swahili"],
            },
            {
                "id": "mm-sw-002",
                "prompt": "M-Pesa inachargia kiasi gani kutuma KES 500?",
                "expected_behavior": (
                    "Ada ya kutuma KES 500 kwa M-Pesa ni KES 11 kwa wasajiliwa "
                    "na KES 33 kwa wasio wasajiliwa (kulingana na bei za 2024)."
                ),
                "language": "sw",
                "domain": "mobile_money",
                "cohort": "informal_economy",
                "provenance": "Safaricom tariff schedule 2024",
                "is_gold": True,
                "is_held_out": False,
                "tags": ["fees", "m-pesa", "swahili"],
            },
            {
                "id": "mm-sw-003-holdout",
                "prompt": "Nawezaje kujua salio langu la M-Pesa?",
                "expected_behavior": "Piga *334# au angalia app ya M-Pesa chini ya 'My Account'.",
                "language": "sw",
                "domain": "mobile_money",
                "cohort": "informal_economy",
                "provenance": "Safaricom USSD guide",
                "is_gold": False,
                "is_held_out": True,  # Never transmitted to models
                "tags": ["balance", "m-pesa", "swahili"],
            },
        ],
    },
    {
        "filename": "customer_service_yo_v1.0.0.jsonl",
        "items": [
            {
                "id": "cs-yo-001",
                "prompt": "Bawo ni mo ṣe le gbe owo ranṣẹ pẹlu MTN Mobile Money?",
                "expected_behavior": (
                    "Lati fi owo ranṣẹ pẹlu MTN MoMo: "
                    "tẹ *165# lori foonu rẹ, yan 'Transfer Money', "
                    "tẹ nọmba foonu olugba, tẹ iye owo, jẹrisi pẹlu PIN rẹ."
                ),
                "language": "yo",
                "domain": "customer_service",
                "cohort": "informal_economy",
                "provenance": "MTN Nigeria MoMo user guide 2024",
                "is_gold": False,
                "is_held_out": False,
                "tags": ["send_money", "mtn-momo", "yoruba"],
            },
        ],
    },
]


def main():
    PACKS_DIR.mkdir(parents=True, exist_ok=True)

    for pack in SEED_PACKS:
        output_path = PACKS_DIR / pack["filename"]
        with output_path.open("w", encoding="utf-8") as f:
            for item in pack["items"]:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        print(f"Seeded {len(pack['items'])} items -> {output_path}")

    print("\nDone. These are DEVELOPMENT SEEDS — not SME-validated.")
    print("Replace with validated items as they arrive from the SME pipeline.")


if __name__ == "__main__":
    main()
