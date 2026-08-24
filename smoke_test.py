"""Smoke test en vivo contra la API real. Ejecutar en tu maquina:

    python smoke_test.py [codigo_postal]

Solo toca endpoints publicos de lectura. No requiere cuenta.
"""

import sys

from mercadona_mcp.client import MercadonaAPI


def main() -> None:
    pc = sys.argv[1] if len(sys.argv) > 1 else "28001"
    api = MercadonaAPI()

    print(f"[1/4] set_postal_code({pc})")
    print("   ->", api.set_postal_code(pc))

    print("[2/4] get_categories()")
    cats = api.get_categories()
    results = cats.get("results", [])
    print(f"   -> {len(results)} categorias raiz. Primera: {results[0]['name'] if results else 'N/A'}")

    print("[3/4] search('leche', limit=3)")
    for hit in api.search("leche", limit=3):
        print(f"   -> [{hit['id']}] {hit['name']} ({hit['packaging']}): {hit['unit_price_eur']} EUR")

    print("[4/4] get_product(<primer resultado>)")
    first = api.search("aceite oliva", limit=1)
    if first:
        prod = api.get_product(first[0]["id"])
        print("   ->", prod.get("display_name"), "|", (prod.get("price_instructions") or {}).get("unit_price"), "EUR")

    print("\nOK: endpoints publicos operativos.")


if __name__ == "__main__":
    main()
