"""Demo data so the dashboard works before the backend is ready.
Same format as agreed in CONTRIBUTING.md: {"name", "logo_url", "source_url"}.
"""

def _c(name, url="https://example.com/customers"):
    return {"name": name, "logo_url": "", "source_url": url}


MOCK_OLD = [_c(n, "https://web.archive.org/web/2023/https://example.com/") for n in
            ["Nokia", "Kone", "Wärtsilä", "Elisa", "Fiskars", "Valmet", "Fazer", "Finnair"]]

MOCK_NEW = [_c(n) for n in
            ["Nokia", "Kone", "Valmet", "Fazer", "Neste", "Supercell"]]
