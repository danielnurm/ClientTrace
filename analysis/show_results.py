import json

with open("data/current.json", "r", encoding="utf-8") as file:
    data = json.load(file)

results = data["results"].get("results", [])

for i, item in enumerate(results, 1):
    print(f"{i}. {item.get('title')}")
    print(f"   URL: {item.get('url')}")
    print()