
import json

with open("data/current.json", "r", encoding="utf-8") as file:
    data = json.load(file)

customers = data.get("customers", [])

print(f"\nLÖYDETTY {len(customers)} ASIAKASTAPAUSTA\n")

for i, customer in enumerate(customers, 1):
    evidence = customer.get("evidence", "")

    print("=" * 60)
    print(f"ASIAKASTAPAUS {i}")
    print("Yritys:", customer.get("company", "Ei tietoa"))
    print("Lähde:", customer.get("source_url", "Ei tietoa"))
    print("Tekstin pituus:", len(evidence))
    print("\nNäyte sisällöstä:")
    print(evidence[:700])
    print()
