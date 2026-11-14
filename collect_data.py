
import json
import time
from datetime import datetime, timezone
from backend.context_api import search_web, scrape_page


def clean_customer_story(markdown):
    """Poimii asiakastarinan ja jättää alatunnisteet pois."""

    start_markers = ["## ", "Until ", "When ", "How ", "We ", "Our "]
    end_markers = [
        "Get started",
        "See it work on your own account list.",
        "More stories",
        "All customer stories"
    ]

    lines = markdown.splitlines()
    start_index = 0

    for i, line in enumerate(lines):
        if any(line.strip().startswith(marker) for marker in start_markers):
            start_index = i
            break

    cleaned_lines = []

    for line in lines[start_index:]:
        if any(marker in line for marker in end_markers):
            break
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines).strip()


query = "site:vainu.com/customers/ Vainu customer case studies named customers"

print("Haetaan Vainun asiakasreferenssejä...")

search_result = search_web(query, num_results=10)
results = search_result.get("results", [])

gigantti_url = "https://www.vainu.com/customers/gigantti/"

urls = {}

for item in results:
    url = item.get("url")
    title = item.get("title", "")

    if url and "/customers/" in url:
        if url.rstrip("/") != "https://www.vainu.com/customers":
            urls[url] = title

# Gigantti lisätään myöhemmin tallennetusta tekstistä.
urls.pop(gigantti_url, None)

customers = []
seen_urls = set()

for url, title in urls.items():

    if url in seen_urls:
        continue

    seen_urls.add(url)
    print(f"\nLuetaan: {title}")

    try:
        page = scrape_page(url)
        markdown = page.get("markdown", {}).get("data", "")

        if not markdown or len(markdown) < 500:
            print("Ohitetaan: sisältöä ei löytynyt riittävästi.")
            continue

        cleaned_text = clean_customer_story(markdown)

        if len(cleaned_text) < 300:
            print("Huomio: lyhyt asiakastarina, tallennetaan tarkistettavaksi.")

        customers.append({
            "company": title,
            "provider": "Vainu",
            "relationship_type": "customer_reference",
            "relationship_status": "published_customer_case",
            "confidence": "medium",
            "source_url": url,
            "evidence": cleaned_text if cleaned_text else markdown[:3000],
            "retrieved_at": datetime.now(timezone.utc).isoformat()
        })

        print(f"Asiakastarina tallennettu ({len(cleaned_text)} merkkiä).")

    except Exception as error:
        print(f"Sivun lukeminen epäonnistui: {error}")

    finally:
        time.sleep(5)


# Lisätään Gigantti aiemmin kerätyn asiakastarinan perusteella.
gigantti = {
    "company": "Gigantti",
    "provider": "Vainu",
    "relationship_type": "customer_reference",
    "relationship_status": "published_customer_case",
    "confidence": "high",
    "source_url": gigantti_url,
    "evidence": """Until 2016, Gigantti’s B2B sales mainly consisted of managing the existing B2B client base. Then the strategy changed. "We concluded that we’d concentrate on finding growth from B2B sales," says Commercial Director Tuomo Laukkonen.

"Our salespeople are active users of Vainu. You can get all the information you need about a company in one single view."

Laukkonen introduced Vainu to the Gigantti B2B team in 2016. It became part of the salespeople’s daily work. Company data also helped Gigantti decide where to establish 18 new B2B sales offices. Vainu built a custom integration allowing salespeople to check company credit reports directly from company pages.

Vainu features used:
- Data Updates
- Company Profiles

Use cases:
- Sales prospecting for a new B2B pipeline
- Company research in a single view
- Choosing locations for new B2B sales offices
- Checking company credit reports from the company page in Vainu""",
    "retrieved_at": datetime.now(timezone.utc).isoformat()
}

customers.append(gigantti)

output = {
    "provider": "Vainu",
    "query": query,
    "retrieved_at": datetime.now(timezone.utc).isoformat(),
    "total_found": len(customers),
    "customers": customers
}

with open("data/current.json", "w", encoding="utf-8") as file:
    json.dump(output, file, ensure_ascii=False, indent=2)

print("\nHaku valmis!")
print(f"Löydettiin {len(customers)} asiakasreferenssisivua.")
print("Tulokset tallennettu tiedostoon data/current.json")
