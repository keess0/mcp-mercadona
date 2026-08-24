"""Tests unitarios del cliente con transportes mock de httpx (sin red)."""

import json

import httpx
import pytest

from mercadona_mcp.client import MercadonaAPI, MercadonaError, NotAuthenticatedError

PRODUCT = {
    "id": "34210",
    "display_name": "Pinones ibericos Hacendado",
    "brand": "Hacendado",
    "packaging": "Bote",
    "share_url": "https://tienda.mercadona.es/product/34210/x",
    "price_instructions": {
        "unit_price": "4.55",
        "reference_price": "91.00",
        "reference_format": "kg",
        "unit_size": 0.05,
        "is_new": False,
        "price_decreased": False,
    },
}


def make_api(handler, algolia_handler=None):
    return MercadonaAPI(
        warehouse="vlc1",
        transport=httpx.MockTransport(handler),
        algolia_transport=httpx.MockTransport(algolia_handler or handler),
    )


def test_params_lang_wh():
    def handler(request):
        assert request.url.params["lang"] == "es"
        assert request.url.params["wh"] == "vlc1"
        return httpx.Response(200, json={"count": 0, "results": []})

    api = make_api(handler)
    assert api.get_categories() == {"count": 0, "results": []}


def test_get_product():
    def handler(request):
        assert request.url.path == "/api/products/34210/"
        return httpx.Response(200, json=PRODUCT)

    api = make_api(handler)
    assert api.get_product("34210")["id"] == "34210"


def test_search_compact():
    def algolia(request):
        assert "products_prod_vlc1_es" in str(request.url)
        body = json.loads(request.content)
        assert "query=leche" in body["params"]
        return httpx.Response(200, json={"hits": [PRODUCT]})

    api = make_api(lambda r: httpx.Response(500), algolia_handler=algolia)
    hits = api.search("leche", limit=5)
    assert hits[0]["id"] == "34210"
    assert hits[0]["unit_price_eur"] == "4.55"
    assert hits[0]["reference_format"] == "kg"


def test_search_sort_and_brand():
    def hit(pid, brand, unit, ref):
        return {
            "id": pid,
            "display_name": pid,
            "brand": brand,
            "price_instructions": {
                "unit_price": unit,
                "reference_price": ref,
                "reference_format": "L",
            },
        }

    def algolia(request):
        body = json.loads(request.content)
        assert "hitsPerPage=50" in body["params"]
        return httpx.Response(
            200,
            json={
                "hits": [
                    hit("caro", "Hacendado", "2.50", "2.50"),
                    hit("pack", "Hacendado", "5.76", "0.96"),
                    hit("otra-marca", "Pascual", "0.50", "0.50"),
                    hit("brick", "Hacendado", "0.96", "0.96"),
                ]
            },
        )

    api = make_api(lambda r: httpx.Response(500), algolia_handler=algolia)

    out = api.search("leche", limit=2, sort="reference_price", brand="hacendado")
    assert [h["id"] for h in out] == ["pack", "brick"]

    out = api.search("leche", limit=4, sort="unit_price")
    assert [h["id"] for h in out] == ["otra-marca", "brick", "caro", "pack"]

    with pytest.raises(MercadonaError, match="sort invalido"):
        api.search("leche", sort="precio")


def test_set_postal_code_updates_warehouse():
    def handler(request):
        assert request.method == "PUT"
        assert json.loads(request.content) == {"new_postal_code": "46001"}
        return httpx.Response(
            200, headers={"x-customer-wh": "vlc1", "x-customer-pc": "46001"}, json={}
        )

    api = make_api(handler)
    out = api.set_postal_code("46001")
    assert out == {"postal_code": "46001", "warehouse": "vlc1"}


def test_login_extracts_token_and_customer():
    def handler(request):
        assert request.url.path == "/api/auth/tokens/"
        body = json.loads(request.content)
        assert body == {"username": "a@b.c", "password": "pw"}
        return httpx.Response(200, json={"token": "T123", "customer_id": 42})

    api = make_api(handler)
    out = api.login("a@b.c", "pw")
    assert out["logged_in"] is True
    assert out["customer_id"] == "42"
    assert out["auth_mode"] == "direct"
    assert api.token == "T123"


def test_login_refresh_exchange():
    calls = []

    def handler(request):
        assert request.url.path == "/api/auth/tokens/"
        body = json.loads(request.content)
        calls.append(body)
        if "password" in body:
            return httpx.Response(
                200, json={"customer_id": "uuid-1", "refresh_token": "R1"}
            )
        assert body == {"refresh_token": "R1"}
        return httpx.Response(200, json={"access_token": "A1", "refresh_token": "R2"})

    api = make_api(handler)
    out = api.login("a@b.c", "pw")
    assert out["auth_mode"] == "refresh-exchange"
    assert out["customer_id"] == "uuid-1"
    assert api.token == "A1"
    assert api.refresh_token == "R2"
    assert len(calls) == 2


def test_401_triggers_refresh_and_retry():
    state = {"access": "OLD"}

    def handler(request):
        if request.url.path == "/api/auth/tokens/":
            body = json.loads(request.content)
            if "password" in body:
                return httpx.Response(
                    200, json={"customer_id": "7", "refresh_token": "R1"}
                )
            state["access"] = "NEW"
            return httpx.Response(200, json={"access_token": "NEW"})
        auth = request.headers.get("authorization")
        if auth == "Bearer NEW" and state["access"] == "NEW":
            return httpx.Response(200, json={"lines": []})
        return httpx.Response(401)

    api = make_api(handler)
    api.login("a@b.c", "pw")
    api.token = "OLD"
    assert api.get_cart() == {"lines": []}
    assert api.token == "NEW"


def test_cart_requires_login():
    api = make_api(lambda r: httpx.Response(200, json={}))
    with pytest.raises(NotAuthenticatedError):
        api.get_cart()


def test_add_to_cart_merges_lines():
    state = {"lines": [{"product_id": "111", "quantity": 2.0}]}

    def handler(request):
        if request.url.path == "/api/auth/tokens/":
            return httpx.Response(200, json={"token": "T", "customer_id": 7})
        assert request.headers["authorization"] == "Bearer T"
        if request.method == "GET":
            return httpx.Response(200, json=state)
        if request.method == "PUT":
            sent = json.loads(request.content)
            state["lines"] = sent["lines"]
            return httpx.Response(200, json=state)
        return httpx.Response(404)

    api = make_api(handler)
    api.login("a@b.c", "pw")
    api.add_to_cart("111", 1)
    assert state["lines"] == [{"product_id": "111", "quantity": 3.0}]
    api.add_to_cart("222", 2)
    assert {"product_id": "222", "quantity": 2.0} in state["lines"]
    api.remove_from_cart("111")
    assert state["lines"] == [{"product_id": "222", "quantity": 2.0}]


def test_error_raises():
    api = make_api(lambda r: httpx.Response(500, text="boom"))
    with pytest.raises(MercadonaError):
        api.get_categories()


def order_handler(cart_total):
    def handler(request):
        if request.url.path == "/api/auth/tokens/":
            return httpx.Response(200, json={"token": "T", "customer_id": 7})
        if request.url.path == "/api/customers/7/cart/" and request.method == "GET":
            return httpx.Response(
                200, json={"lines": [], "summary": {"total": cart_total}}
            )
        assert request.url.path == "/api/customers/7/orders/"
        assert json.loads(request.content) == {
            "slot_id": "s1",
            "payment_card_id": "c1",
        }
        return httpx.Response(201, json={"order_id": "O1", "status": "confirmed"})

    return handler


def test_place_order_payload():
    api = make_api(order_handler("75.40"))
    api.login("a@b.c", "pw")
    out = api.place_order(slot_id="s1", payment_card_id="c1")
    assert out["order_id"] == "O1"


def test_place_order_blocked_below_minimum():
    api = make_api(order_handler("42.50"))
    api.login("a@b.c", "pw")
    with pytest.raises(MercadonaError, match="minimo de 60.00 EUR"):
        api.place_order(slot_id="s1", payment_card_id="c1")


def test_place_order_allowed_at_exact_minimum():
    api = make_api(order_handler("60.00"))
    api.login("a@b.c", "pw")
    out = api.place_order(slot_id="s1", payment_card_id="c1")
    assert out["order_id"] == "O1"


# ---------------------------------------------------------------- seguridad


def test_search_limit_is_capped():
    """Un limit desmedido (accidental o via prompt injection) no debe poder
    forzar una peticion desproporcionada a Algolia: se acota a MAX_SEARCH_LIMIT."""
    from mercadona_mcp.client import MAX_SEARCH_LIMIT

    captured = {}

    def algolia(request):
        captured["params"] = json.loads(request.content)["params"]
        return httpx.Response(200, json={"hits": []})

    api = make_api(lambda r: httpx.Response(500), algolia_handler=algolia)
    api.search("leche", limit=999999)

    from urllib.parse import parse_qs

    parsed = parse_qs(captured["params"])
    assert int(parsed["hitsPerPage"][0]) <= MAX_SEARCH_LIMIT * 5


def test_search_limit_rejects_non_positive():
    # limit <= 0 no debe explotar; se acota a un minimo de 1 candidato.
    api = make_api(
        lambda r: httpx.Response(500),
        algolia_handler=lambda r: httpx.Response(200, json={"hits": []}),
    )
    assert api.search("leche", limit=0) == []
    assert api.search("leche", limit=-5) == []


def test_search_escapes_special_characters_in_query():
    """Un query con '&' no debe poder inyectar parametros extra de Algolia
    (ej. hitsPerPage, facetFilters) en el string que se envia como 'params'."""
    captured = {}

    def algolia(request):
        captured["params"] = json.loads(request.content)["params"]
        return httpx.Response(200, json={"hits": []})

    api = make_api(lambda r: httpx.Response(500), algolia_handler=algolia)
    api.search('leche&hitsPerPage=9999&facetFilters=["brand:X"]', limit=5)

    from urllib.parse import parse_qs

    parsed = parse_qs(captured["params"])
    # el query completo (incluido el '&' literal) viaja como valor de 'query',
    # no se cuela como parametros hitsPerPage/facetFilters adicionales
    assert parsed["query"] == ['leche&hitsPerPage=9999&facetFilters=["brand:X"]']
    assert parsed["hitsPerPage"] == ["5"]  # el limit real, no el inyectado (9999)
    assert "facetFilters" not in parsed


@pytest.mark.parametrize(
    "bad_path",
    [
        "https://attacker.example.com/steal",
        "HTTP://attacker.example.com/steal",
        "//attacker.example.com/steal",
        "https:attacker.example.com/steal",
        "/api/../../evil",
        "customers/7/cart/",
    ],
)
def test_raw_request_rejects_unsafe_paths(bad_path):
    """raw_request no debe poder salir de /api en tienda.mercadona.es: una
    URL absoluta se enviaria (con el Authorization real) a un host arbitrario,
    porque httpx ignora base_url en cuanto el argumento trae esquema/host."""
    api = make_api(lambda r: httpx.Response(200, json={}))
    out = api.raw_request("GET", bad_path)
    assert "error" in out
    assert "path invalido" in out["error"]


def test_raw_request_allows_relative_path():
    def handler(request):
        assert str(request.url) == "https://tienda.mercadona.es/api/categories/?lang=es&wh=vlc1"
        return httpx.Response(200, json={"ok": True})

    api = make_api(handler)
    out = api.raw_request("GET", "/categories/", authenticated=False)
    assert out == {"status": 200, "body": {"ok": True}}


def test_get_product_encodes_path_traversal_attempt():
    def handler(request):
        # el '/' de los ".." va codificado como %2F en el request real (raw_path),
        # asi que el servidor lo ve como un unico segmento de recurso, no como
        # separadores de ruta que permitan escapar de /products/. request.url.path
        # decodifica %2F de vuelta a '/' solo para lectura en Python, no es lo que
        # viaja por la red.
        assert request.url.raw_path.startswith(
            b"/api/products/..%2F..%2Fauth%2Ftokens/"
        )
        return httpx.Response(200, json={"id": "x"})

    api = make_api(handler)
    api.get_product("../../auth/tokens")
