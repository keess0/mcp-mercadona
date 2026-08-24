"""Cliente HTTP para la API no oficial de tienda.mercadona.es.

Capas:
  - Catalogo (publico, sin auth): categorias, productos, novedades, bajadas de precio.
  - Busqueda (Algolia, claves publicas del frontend).
  - Cuenta (privado, requiere token): carrito, pedidos, direcciones, tarjetas.

Los endpoints privados estan obtenidos por ingenieria inversa del frontend y
pueden cambiar sin aviso. `raw_request` permite adaptarse sin tocar el codigo.
"""

from __future__ import annotations

import os
import uuid
from typing import Any, Optional
from urllib.parse import quote, urlencode

import httpx

BASE_URL = "https://tienda.mercadona.es/api"
ALGOLIA_URL = "https://7uzjkl1dj0-dsn.algolia.net/1/indexes/products_prod_{wh}_es/query"
ALGOLIA_APP_ID = "7UZJKL1DJ0"
ALGOLIA_API_KEY = "9d8f2e39e90df472b4f2e559a116fe17"

DEFAULT_WAREHOUSE = "mad1"
MAX_SEARCH_LIMIT = 100
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) mercadona-mcp/0.1"


class MercadonaError(RuntimeError):
    pass


class NotAuthenticatedError(MercadonaError):
    pass


def _compact_product(p: dict) -> dict:
    pi = p.get("price_instructions") or {}
    return {
        "id": p.get("id"),
        "name": p.get("display_name"),
        "brand": p.get("brand"),
        "packaging": p.get("packaging"),
        "unit_price_eur": pi.get("unit_price"),
        "reference_price_eur": pi.get("reference_price"),
        "reference_format": pi.get("reference_format"),
        "unit_size": pi.get("unit_size"),
        "is_new": pi.get("is_new"),
        "price_decreased": pi.get("price_decreased"),
        "share_url": p.get("share_url"),
    }


class MercadonaAPI:
    def __init__(
        self,
        lang: str = "es",
        warehouse: Optional[str] = None,
        transport: Optional[httpx.BaseTransport] = None,
        algolia_transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self.lang = lang
        self.warehouse = warehouse or os.getenv("MERCADONA_WAREHOUSE", DEFAULT_WAREHOUSE)
        self.postal_code: Optional[str] = os.getenv("MERCADONA_POSTAL_CODE")
        self.token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.customer_id: Optional[str] = None
        self.auth_scheme = os.getenv("MERCADONA_AUTH_SCHEME", "Bearer")
        headers = {
            "user-agent": USER_AGENT,
            "x-customer-device-id": str(uuid.uuid4()),
            "accept": "application/json",
        }
        self._http = httpx.Client(
            base_url=BASE_URL, headers=headers, timeout=20.0, transport=transport
        )
        self._algolia = httpx.Client(timeout=20.0, transport=algolia_transport)

    # ------------------------------------------------------------------ util

    def _params(self, extra: Optional[dict] = None) -> dict:
        params = {"lang": self.lang, "wh": self.warehouse}
        if extra:
            params.update(extra)
        return params

    def _auth_headers(self) -> dict:
        if self.token:
            value = (
                f"{self.auth_scheme} {self.token}".strip()
                if self.auth_scheme
                else self.token
            )
            return {"authorization": value}
        if self._http.cookies:
            return {}
        raise NotAuthenticatedError(
            "No hay sesion iniciada. Usa login() primero "
            "(credenciales via MERCADONA_EMAIL / MERCADONA_PASSWORD)."
        )

    def _request(
        self,
        method: str,
        path: str,
        json: Any = None,
        params: Optional[dict] = None,
        authenticated: bool = False,
        _retry: bool = True,
    ) -> httpx.Response:
        headers = self._auth_headers() if authenticated else {}
        resp = self._http.request(
            method, path, json=json, params=self._params(params), headers=headers
        )
        if resp.status_code == 401 and authenticated and _retry and self.refresh_token:
            self._refresh_session()
            return self._request(method, path, json, params, authenticated, _retry=False)
        if resp.status_code == 401:
            raise NotAuthenticatedError(
                f"401 en {path}: token ausente o caducado. Vuelve a hacer login."
            )
        if resp.status_code >= 400:
            raise MercadonaError(
                f"{method} {path} -> {resp.status_code}: {resp.text[:500]}"
            )
        return resp

    @staticmethod
    def _json(resp: httpx.Response) -> Any:
        if resp.status_code == 204 or not resp.content:
            return {"status": resp.status_code}
        return resp.json()

    # --------------------------------------------------------------- catalogo

    def get_categories(self) -> Any:
        return self._json(self._request("GET", "/categories/"))

    def get_category(self, category_id: int, compact: bool = True) -> Any:
        data = self._json(
            self._request("GET", f"/categories/{quote(str(category_id), safe='')}/")
        )
        if not compact or not isinstance(data, dict):
            return data
        out = {"id": data.get("id"), "name": data.get("name"), "subcategories": []}
        for sub in data.get("categories", []):
            out["subcategories"].append(
                {
                    "id": sub.get("id"),
                    "name": sub.get("name"),
                    "products": [_compact_product(p) for p in sub.get("products", [])],
                }
            )
        return out

    def get_product(self, product_id: str) -> Any:
        pid = quote(str(product_id), safe="")
        return self._json(self._request("GET", f"/products/{pid}/"))

    def get_similar_products(self, product_id: str) -> Any:
        pid = quote(str(product_id), safe="")
        data = self._json(self._request("GET", f"/products/{pid}/similars/"))
        if isinstance(data, dict) and "results" in data:
            return [_compact_product(p) for p in data["results"]]
        return data

    def get_new_arrivals(self) -> Any:
        return self._json(self._request("GET", "/home/new-arrivals/"))

    def get_price_drops(self) -> Any:
        return self._json(self._request("GET", "/home/price-drops/"))

    def set_postal_code(self, postal_code: str) -> dict:
        resp = self._request(
            "PUT",
            "/postal-codes/actions/change-pc/",
            json={"new_postal_code": postal_code},
        )
        wh = resp.headers.get("x-customer-wh")
        if wh:
            self.warehouse = wh
        self.postal_code = resp.headers.get("x-customer-pc", postal_code)
        return {"postal_code": self.postal_code, "warehouse": self.warehouse}

    def search(
        self,
        query: str,
        limit: int = 10,
        full: bool = False,
        sort: str = "relevance",
        brand: Optional[str] = None,
    ) -> Any:
        if sort not in ("relevance", "unit_price", "reference_price"):
            raise MercadonaError(
                f"sort invalido: {sort!r}. Usa relevance, unit_price o reference_price."
            )
        # limit acotado: un valor desmedido (accidental o via prompt injection)
        # no debe poder forzar peticiones desproporcionadas a Algolia.
        limit = max(1, min(int(limit), MAX_SEARCH_LIMIT))
        fetch = limit if sort == "relevance" and not brand else max(limit * 5, 50)
        url = ALGOLIA_URL.format(wh=self.warehouse)
        resp = self._algolia.post(
            url,
            params={
                "x-algolia-application-id": ALGOLIA_APP_ID,
                "x-algolia-api-key": ALGOLIA_API_KEY,
            },
            json={"params": urlencode({"query": query, "hitsPerPage": fetch})},
        )
        if resp.status_code >= 400:
            raise MercadonaError(f"Algolia -> {resp.status_code}: {resp.text[:300]}")
        hits = resp.json().get("hits", [])
        if brand:
            hits = [h for h in hits if (h.get("brand") or "").lower() == brand.lower()]
        if sort != "relevance":
            key = "reference_price" if sort == "reference_price" else "unit_price"

            def price_of(h: dict) -> float:
                try:
                    return float((h.get("price_instructions") or {}).get(key))
                except (TypeError, ValueError):
                    return float("inf")

            hits = sorted(hits, key=price_of)
        hits = hits[:limit]
        if full:
            return hits
        return [_compact_product(h) for h in hits]

    # ----------------------------------------------------------------- cuenta

    @staticmethod
    def _extract_auth(data: Any) -> tuple[Optional[str], Optional[str], Optional[str]]:
        if not isinstance(data, dict):
            return None, None, None
        access = (
            data.get("access_token")
            or data.get("token")
            or data.get("access")
            or data.get("auth_token")
        )
        refresh = data.get("refresh_token") or data.get("refresh")
        customer = data.get("customer") or {}
        customer_id = data.get("customer_id") or customer.get("id")
        return (
            str(access) if access else None,
            str(refresh) if refresh else None,
            str(customer_id) if customer_id is not None else None,
        )

    def _refresh_session(self) -> None:
        if not self.refresh_token:
            raise NotAuthenticatedError("Sin refresh_token: haz login primero.")
        resp = self._http.request(
            "POST",
            "/auth/tokens/",
            json={"refresh_token": self.refresh_token},
            params=self._params(),
        )
        if resp.status_code >= 400:
            raise NotAuthenticatedError(
                f"Refresh fallido ({resp.status_code}): {resp.text[:300]}. "
                "Vuelve a hacer login."
            )
        data = self._json(resp)
        access, refresh, customer_id = self._extract_auth(data)
        if refresh:
            self.refresh_token = refresh
        if customer_id:
            self.customer_id = customer_id
        if access:
            self.token = access
        elif not self._http.cookies:
            raise MercadonaError(
                "El refresh no devolvio access token ni cookies de sesion. "
                f"Claves de la respuesta: {sorted(data) if isinstance(data, dict) else type(data)}"
            )

    def login(self, email: Optional[str] = None, password: Optional[str] = None) -> dict:
        email = email or os.getenv("MERCADONA_EMAIL")
        password = password or os.getenv("MERCADONA_PASSWORD")
        if not email or not password:
            raise MercadonaError(
                "Faltan credenciales. Define MERCADONA_EMAIL y MERCADONA_PASSWORD "
                "en el entorno del servidor MCP (recomendado) o pasalas como argumento."
            )
        resp = self._request(
            "POST", "/auth/tokens/", json={"username": email, "password": password}
        )
        data = self._json(resp)
        access, refresh, customer_id = self._extract_auth(data)
        self.customer_id = customer_id or self.customer_id
        self.refresh_token = refresh
        auth_mode = "direct"
        if access:
            self.token = access
        elif refresh:
            self._refresh_session()
            auth_mode = "refresh-exchange"
        else:
            raise MercadonaError(
                f"Login sin token reconocible. Respuesta: {str(data)[:300]}"
            )
        cookies = sorted(c for c in self._http.cookies.keys())
        return {
            "logged_in": True,
            "customer_id": self.customer_id,
            "auth_mode": auth_mode,
            "has_access_token": bool(self.token),
            "session_cookies": cookies,
        }

    def _require_customer(self) -> str:
        if not self.customer_id:
            raise NotAuthenticatedError("customer_id desconocido: haz login primero.")
        return self.customer_id

    def get_cart(self) -> Any:
        cid = self._require_customer()
        return self._json(self._request("GET", f"/customers/{cid}/cart/", authenticated=True))

    def update_cart(self, lines: list[dict]) -> Any:
        cid = self._require_customer()
        payload = {
            "lines": [
                {"product_id": str(l["product_id"]), "quantity": float(l["quantity"])}
                for l in lines
            ]
        }
        return self._json(
            self._request("PUT", f"/customers/{cid}/cart/", json=payload, authenticated=True)
        )

    def add_to_cart(self, product_id: str, quantity: float = 1) -> Any:
        cart = self.get_cart()
        lines: list[dict] = []
        found = False
        for line in cart.get("lines", []) if isinstance(cart, dict) else []:
            pid = str(line.get("product_id") or (line.get("product") or {}).get("id"))
            qty = float(line.get("quantity", 0))
            if pid == str(product_id):
                qty += float(quantity)
                found = True
            lines.append({"product_id": pid, "quantity": qty})
        if not found:
            lines.append({"product_id": str(product_id), "quantity": float(quantity)})
        return self.update_cart(lines)

    def remove_from_cart(self, product_id: str) -> Any:
        cart = self.get_cart()
        lines = [
            {
                "product_id": str(l.get("product_id") or (l.get("product") or {}).get("id")),
                "quantity": float(l.get("quantity", 0)),
            }
            for l in (cart.get("lines", []) if isinstance(cart, dict) else [])
        ]
        lines = [l for l in lines if l["product_id"] != str(product_id)]
        return self.update_cart(lines)

    def get_orders(self) -> Any:
        cid = self._require_customer()
        return self._json(
            self._request("GET", f"/customers/{cid}/orders/", authenticated=True)
        )

    def get_addresses(self) -> Any:
        cid = self._require_customer()
        return self._json(
            self._request("GET", f"/customers/{cid}/addresses/", authenticated=True)
        )

    def get_payment_cards(self) -> Any:
        cid = self._require_customer()
        return self._json(
            self._request("GET", f"/customers/{cid}/payment-cards/", authenticated=True)
        )

    def place_order(
        self,
        slot_id: Optional[str] = None,
        address_id: Optional[str] = None,
        payment_card_id: Optional[str] = None,
    ) -> Any:
        cid = self._require_customer()
        minimum = float(os.getenv("MERCADONA_MIN_ORDER_EUR", "60"))
        cart = self.get_cart()
        try:
            total = float((cart.get("summary") or {}).get("total", 0))
        except (TypeError, ValueError):
            total = 0.0
        if total < minimum:
            raise MercadonaError(
                f"Pedido no realizado: el carrito suma {total:.2f} EUR y Mercadona "
                f"exige un minimo de {minimum:.2f} EUR por pedido. "
                f"Faltan {minimum - total:.2f} EUR."
            )
        payload: dict[str, Any] = {}
        if slot_id:
            payload["slot_id"] = slot_id
        if address_id:
            payload["address_id"] = address_id
        if payment_card_id:
            payload["payment_card_id"] = payment_card_id
        return self._json(
            self._request(
                "POST", f"/customers/{cid}/orders/", json=payload, authenticated=True
            )
        )

    # ------------------------------------------------------------ exploracion

    @staticmethod
    def _validate_relative_path(path: str) -> None:
        """Bloquea URLs absolutas y traversal: raw_request solo debe poder
        tocar rutas relativas dentro de /api en tienda.mercadona.es. httpx
        trata cualquier argumento con esquema (http://, https://...) como URL
        absoluta e ignora base_url por completo -- sin este chequeo, un path
        como 'https://atacante.com/x' enviaria el header Authorization (token
        de la cuenta) a un host arbitrario."""
        if not path.startswith("/") or path.startswith("//"):
            raise MercadonaError(
                f"path invalido: {path!r}. Debe ser una ruta relativa que empiece "
                "por '/', ej. '/customers/<id>/cart/'."
            )
        if "://" in path or ":" in path.split("/", 1)[0]:
            raise MercadonaError(
                f"path invalido: {path!r}. No se permiten URLs absolutas ni "
                "esquemas (http:, https:, etc.) en raw_request."
            )
        if ".." in path.split("/"):
            raise MercadonaError(
                f"path invalido: {path!r}. No se permiten segmentos '..' "
                "(traversal fuera de /api)."
            )

    def raw_request(
        self, method: str, path: str, json_body: Any = None, authenticated: bool = True
    ) -> dict:
        try:
            self._validate_relative_path(path)
            resp = self._request(
                method.upper(), path, json=json_body, authenticated=authenticated
            )
            return {"status": resp.status_code, "body": self._json(resp)}
        except MercadonaError as exc:
            return {"error": str(exc)}
