# Manual check, not a pytest test: calls Context.dev and costs credits on every run.

from backend.context_api import search_web

try:
    result = search_web("Finnish companies customer references")
    print("API-YHTEYS ONNISTUI!")
    print(result)

except Exception as error:
    print("API-TESTI EPÄONNISTUI:")
    print(error)
