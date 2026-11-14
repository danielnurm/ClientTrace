"""
Laita .env tiedostoon 

OPENAI_API_KEY = "{key tähän}"

"""


import os
import json
from openai import OpenAI
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class CustomerMatch(BaseModel):
    old_customer: str
    new_customer: str | None
    is_match: bool
    reason: str


class ComparisonResult(BaseModel):
    matches: list[CustomerMatch]


def compare_customers(
    old_customers: list[str],
    new_customers: list[str]
) -> dict[str, list[str]]:

    # Jos molemmat listat ovat tyhjiä
    if not old_customers and not new_customers:
        return {"lost": [], "retained": [], "added": []}

    # Jos vanha lista on tyhjä, kaikki asiakkaat ovat uusia
    if not old_customers:
        return {
            "lost": [],
            "retained": [],
            "added": new_customers
        }

    # Jos uusi lista on tyhjä, kaikki vanhat asiakkaat ovat kadonneet
    if not new_customers:
        return {
            "lost": old_customers,
            "retained": [],
            "added": []
        }

    response = client.responses.parse(
        model="gpt-4o-mini",
        input=[
            {
                "role": "system",
                "content": """
                You are an expert at matching company names.

                Determine whether companies in old_customers and
                new_customers refer to the same company.

                Consider:
                - Capitalization differences
                - Legal suffixes (Oy, Oyj, Ltd, Inc, Corporation)
                - Minor spelling differences
                - Known company aliases

                Examples:
                - Nokia = Nokia Oyj
                - Teboil = TeboiL
                - Microsoft = Microsoft Corporation

                Rules:
                - Each old customer must be matched at most once.
                - Each new customer must be matched at most once.
                - Only match companies that are genuinely the same entity.
                - If uncertain, do not match.
                - Return every old customer exactly once.
                - Use null as new_customer if no match exists.
                """
            },
            {
                "role": "user",
                "content": json.dumps({
                    "old_customers": old_customers,
                    "new_customers": new_customers
                })
            }
        ],
        text_format=ComparisonResult
    )

    result = response.output_parsed

    if result is None:
        raise ValueError("AI could not compare the customer lists.")

    # Muodostetaan palautettavat listat
    lost = []
    retained = []

    matched_new_customers = set()

    for match in result.matches:
        if match.is_match and match.new_customer is not None:
            retained.append(match.new_customer)
            matched_new_customers.add(match.new_customer)
        else:
            lost.append(match.old_customer)

    # Asiakkaat, joita ei löytynyt vanhasta listasta
    added = [
        customer
        for customer in new_customers
        if customer not in matched_new_customers
    ]

    return {
        "lost": lost,
        "retained": retained,
        "added": added
    }




old = ["Nokia", "Teboil", "Apple"]
new = ["Nokia Oyj", "TeboiL", "Google"]

result = compare_customers(old, new)

print(result)