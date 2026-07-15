"""Quick verification that the benchmark loader works correctly."""
import sys

sys.path.insert(0, ".")

from benchmarks.loader import list_available_packs, load_pack

packs = list_available_packs()
print(f"Available packs: {[p['filename'] for p in packs]}")

items = load_pack("mobile_money_sw", "v1.0.0")
print(f"Loaded {len(items)} items (held-out excluded)")
for item in items:
    print(f"  [{item['language']}] {item['prompt'][:55]}...")
    print(f"    gold={item['is_gold']} cohort={item['cohort']}")

print("\nBenchmark loader: OK")
