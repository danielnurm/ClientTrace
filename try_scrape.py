# Manual check, not a pytest test: calls Context.dev and costs credits on every run.
import json
from backend.context_api import scrape_page

url = "https://www.vainu.com/customers/billetto/"

print("Haetaan Billetton asiakastapausta...")

result = scrape_page(url)

with open("data/billetto.json", "w", encoding="utf-8") as file:
    json.dump(result, file, ensure_ascii=False, indent=2)

print("Haku onnistui!")
print("Tallennettu tiedostoon data/billetto.json")

markdown = result.get("markdown", {}).get("data", "")
print("\nSIVUN SISÄLTÖ:")
print(markdown[:3000])