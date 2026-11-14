
import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("CONTEXT_DEV_API_KEY")

BASE_URL = "https://api.context.dev/v1"


def search_web(query, num_results=5):
    """Search the web using Context.dev."""

    if not API_KEY:
        raise ValueError("Context.dev API key is missing from .env")

    url = f"{BASE_URL}/web/search"

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "query": query,
        "numResults": num_results,
        "markdownOptions": {
            "enabled": True
        }
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=90
    )

    response.raise_for_status()
    return response.json()


def scrape_page(url):
    """Retrieve webpage content as Markdown."""

    if not API_KEY:
        raise ValueError("Context.dev API key is missing from .env")

    endpoint = f"{BASE_URL}/web/scrape"

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "url": url,
        "formats": {
            "markdown": True
        }
    }

    response = requests.post(
        endpoint,
        headers=headers,
        json=payload,
        timeout=90
    )

    response.raise_for_status()
    return response.json()
