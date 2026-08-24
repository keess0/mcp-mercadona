"""Servidor MCP (stdio) para tienda.mercadona.es construido con FastMCP.

Tools de catalogo (sin cuenta), de cuenta (login/carrito/pedidos), de pago
y de preferencias persistentes del usuario.
El pago exige confirmacion explicita: confirm="CONFIRMO EL PAGO".
"""

from __future__ import annotations

import os
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from mercadona_mcp.client import MercadonaAPI, MercadonaError
from mercadona_mcp.prefs import Preferences

mcp = FastMCP("mercadona")
api = MercadonaAPI()
prefs = Preferences()

CONFIRM_PHRASE = "CONFIRMO EL PAGO"


@mcp.tool()
def set_postal_code(postal_code: str) -> dict:
    """Fija el codigo postal de entrega y resuelve el almacen (wh) que sirve la zona.
    Llamalo antes de consultar precios si el usuario no esta en Madrid (por defecto mad1),
    porque precios y disponibilidad dependen del almacen."""
    return api.set_postal_code(postal_code)


@mcp.tool()
def search_products(
    query: str,
    limit: int = 10,
    sort: str = "relevance",
    brand: Optional[str] = None,
) -> Any:
    """Busca productos por texto libre (ej. 'leche entera', 'pizza barbacoa').
    Devuelve id, nombre, marca, precio unitario y precio de referencia (EUR).
    sort: 'relevance' (orden del buscador), 'reference_price' (mas barato por
    kg/L primero — usalo cuando el usuario quiera ahorrar) o 'unit_price'
    (envase mas barato primero). brand filtra por marca exacta (ej. 'Hacendado').
    Ojo con sort='reference_price' si la busqueda mezcla formatos kg y L:
    comprueba reference_format al comparar. limit se acota internamente a 100."""
    return api.search(query, limit=limit, sort=sort, brand=brand)


@mcp.tool()
def get_categories() -> Any:
    """Arbol de categorias de la tienda (dos niveles). Util para explorar el catalogo."""
    return api.get_categories()


@mcp.tool()
def get_category_products(category_id: int) -> Any:
    """Lista los productos de una categoria concreta con precios compactos."""
    return api.get_category(category_id)


@mcp.tool()
def get_product(product_id: str) -> Any:
    """Ficha completa de un producto: precio, formato, ingredientes, alergenos, fotos."""
    return api.get_product(product_id)


@mcp.tool()
def get_similar_products(product_id: str) -> Any:
    """Productos similares/alternativos a uno dado."""
    return api.get_similar_products(product_id)


@mcp.tool()
def get_new_arrivals() -> Any:
    """Novedades de la tienda."""
    return api.get_new_arrivals()


@mcp.tool()
def get_price_drops() -> Any:
    """Productos con bajada de precio reciente."""
    return api.get_price_drops()


@mcp.tool()
def login(email: Optional[str] = None, password: Optional[str] = None) -> dict:
    """Inicia sesion en la cuenta de Mercadona del usuario.
    Por seguridad, lo recomendado es NO pasar credenciales por el chat: definelas como
    variables de entorno MERCADONA_EMAIL y MERCADONA_PASSWORD en la config del servidor
    y llama a esta tool sin argumentos."""
    return api.login(email, password)


@mcp.tool()
def get_cart() -> Any:
    """Devuelve el carrito actual de la cuenta (requiere login)."""
    return api.get_cart()


@mcp.tool()
def add_to_cart(product_id: str, quantity: float = 1) -> Any:
    """Anade un producto al carrito (requiere login). quantity admite decimales
    para productos a granel vendidos por peso."""
    return api.add_to_cart(product_id, quantity)


@mcp.tool()
def remove_from_cart(product_id: str) -> Any:
    """Elimina un producto del carrito (requiere login)."""
    return api.remove_from_cart(product_id)


@mcp.tool()
def get_orders() -> Any:
    """Historial de pedidos de la cuenta (requiere login)."""
    return api.get_orders()


@mcp.tool()
def get_addresses() -> Any:
    """Direcciones de entrega guardadas (requiere login)."""
    return api.get_addresses()


@mcp.tool()
def get_payment_cards() -> Any:
    """Tarjetas de pago guardadas en la cuenta (requiere login). Solo metadatos,
    nunca el PAN completo."""
    return api.get_payment_cards()


@mcp.tool()
def place_order(
    confirm: str,
    slot_id: Optional[str] = None,
    address_id: Optional[str] = None,
    payment_card_id: Optional[str] = None,
) -> Any:
    """Confirma el pedido y ejecuta el PAGO REAL con la tarjeta guardada.
    IRREVERSIBLE una vez aceptado por Mercadona.
    Deshabilitado por defecto: requiere MERCADONA_ENABLE_CHECKOUT=1 en el
    entorno del servidor ademas de la confirmacion explicita.
    Verifica antes que el carrito alcanza el pedido minimo de Mercadona
    (60 EUR, configurable con MERCADONA_MIN_ORDER_EUR); si no llega, falla
    sin ejecutar nada.
    Antes de llamar: muestra al usuario el carrito y el importe total y pide su
    aprobacion explicita. Solo procede si el usuario ha aprobado; entonces pasa
    confirm="CONFIRMO EL PAGO". Endpoint de checkout obtenido por ingenieria
    inversa: si falla, usa raw_api_request para inspeccionar el flujo real."""
    if os.getenv("MERCADONA_ENABLE_CHECKOUT", "").strip().lower() not in (
        "1",
        "true",
        "yes",
    ):
        raise MercadonaError(
            "place_order deshabilitado: define MERCADONA_ENABLE_CHECKOUT=1 en el "
            "entorno del servidor para permitir pagos reales. Salvaguarda para "
            "evitar pagos accidentales en clientes MCP que autoejecutan tools "
            "sin confirmacion humana."
        )
    if confirm != CONFIRM_PHRASE:
        raise MercadonaError(
            f"Pago no ejecutado: se requiere confirm='{CONFIRM_PHRASE}' "
            "tras aprobacion explicita del usuario."
        )
    return api.place_order(slot_id, address_id, payment_card_id)


@mcp.tool()
def get_preferences() -> dict:
    """Preferencias de compra guardadas del usuario (huevos camperos, leche
    semidesnatada, prioridad al precio por kg, marcas, eco, etc.).
    LLAMALA SIEMPRE antes de elegir productos o resolver ambiguedades: si la
    respuesta ya esta aqui, no se lo preguntes otra vez al usuario."""
    return prefs.get_all()


@mcp.tool()
def set_preference(key: str, value: str) -> dict:
    """Guarda o actualiza una preferencia de compra del usuario para futuras
    sesiones. Usala proactivamente cuando el usuario exprese una preferencia,
    elija entre opciones que le presentes, o corrija tu eleccion — sin pedir
    permiso para recordarlo. key = categoria corta ('huevos', 'leche',
    'criterio_precio'); value = la preferencia en texto claro
    (ej. 'camperos o libres de jaula; nunca de suelo')."""
    return prefs.set(key, value)


@mcp.tool()
def delete_preference(key: str) -> dict:
    """Elimina una preferencia guardada (si el usuario cambia de opinion o
    pide olvidarla)."""
    return prefs.delete(key)


@mcp.tool()
def raw_api_request(
    method: str, path: str, json_body: Any = None, authenticated: bool = True
) -> dict:
    """Peticion arbitraria a https://tienda.mercadona.es/api para explorar o adaptar
    endpoints privados no documentados (ej. '/customers/<id>/cart/'). path debe ser
    una ruta relativa que empiece por '/' (sin esquema, sin host, sin '..'); URLs
    absolutas o traversal se rechazan para no filtrar el token de sesion a un host
    ajeno. La respuesta se devuelve tal cual la de Mercadona: si el endpoint elegido
    expone datos sensibles (tokens, direcciones, tarjetas), apareceran en el
    resultado sin filtrar -- no compartas esa salida en transcripciones publicas.
    Herramienta de depuracion: nunca la uses para ejecutar pagos."""
    return api.raw_request(method, path, json_body, authenticated)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
