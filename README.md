# ClientTrace

Enter a company URL → see which customer logos have disappeared since 2023.

## Roles
1. Context.dev, current customers – `backend/context_api.py`
2. Wayback Machine, historical customers – `backend/wayback.py`
3. Comparison + AI – `analysis/`
4. Dashboard – `app.py`, `frontend/`

## Agreed functions (DO NOT change names or formats without asking)
```python
# backend/context_api.py
get_current_customers(url: str) -> list[dict]

# backend/wayback.py
get_historical_customers(url: str, year: int) -> list[dict]

# analysis/comparison.py
compare_customers(old: list[dict], new: list[dict]) -> dict
# returns {"lost": [...], "retained": [...], "added": [...]}
```

A customer always has this format:
```json
{"name": "Nokia", "logo_url": "https://...", "source_url": "https://..."}
```

## Git rules
- No direct pushes to `main`. Everyone works on their own branch.
- Run `git pull origin main` before you start working.
- When your part works → Pull request → someone takes a quick look → merge.
- API keys go only in `.env`, never in the code.

## Running
```bash
pip install -r requirements.txt
streamlit run app.py
```
