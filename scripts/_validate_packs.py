import sys

sys.path.insert(0, ".")
from benchmarks.loader import load_pack

packs = [
    ("agriculture_om", "v1.0.0"),
    ("cross_border_trade_ha", "v1.0.0"),
    ("urban_digital_sheng", "v1.0.0"),
    ("remittance_so", "v1.0.0"),
    ("public_services_zu", "v1.0.0"),
]

all_ok = True
for name, version in packs:
    try:
        items = load_pack(name, version)
        print(f"{name}: {len(items)} active items")
        for item in items:
            print(f"  {item['id']}")
    except Exception as e:
        print(f"ERROR {name}: {e}")
        all_ok = False

print("\nAll packs OK" if all_ok else "\nSOME PACKS FAILED")
