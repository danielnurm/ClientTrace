"""Analysis-paketti. Raskaat importit (OpenAI) ladataan vasta käytössä."""

from __future__ import annotations

from typing import Any


def __getattr__(name: str) -> Any:
    if name == "analyze_customers":
        from analysis.ai_analysis import analyze_customers

        return analyze_customers
    if name == "compare_customers":
        from analysis.comparison import compare_customers

        return compare_customers
    if name in {
        "apply_normalization",
        "customer_names",
        "normalize_company_names",
    }:
        from analysis import customer_extraction

        return getattr(customer_extraction, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "analyze_customers",
    "apply_normalization",
    "compare_customers",
    "customer_names",
    "normalize_company_names",
]
