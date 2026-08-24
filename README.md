# mercadona-mcp

Servidor MCP no oficial para `tienda.mercadona.es`. Servidor MCP estándar (FastMCP sobre stdio): funciona con Claude Desktop/Code y con cualquier otro cliente que hable el protocolo MCP. Permite buscar productos y precios, gestionar el carrito de tu cuenta y, con confirmación explícita y `MERCADONA_ENABLE_CHECKOUT` activado, pagar un pedido.

**Aviso**: Mercadona no ofrece API pública. Este proyecto usa endpoints obtenidos por ingeniería inversa que pueden romperse sin aviso y cuyo uso automatizado puede incumplir los ToS de Mercadona. Detalles técnicos en [API_STUDY.md](API_STUDY.md).

**Estado (julio 2026)**: verificado en vivo contra cuenta real — catálogo, búsqueda, login (JWT en dos pasos con auto-refresh en 401), lectura/escritura de carrito, pedidos, direcciones y tarjetas. Único flujo sin verificar: `place_order` (requiere cuenta con dirección y tarjeta guardadas).

## Instalación

```bash
cd C:\ruta\a\MCP_Mercadona
pip install -e .
```

Verifica los endpoints públicos en vivo:

```bash
python smoke_test.py 28001
```

Tests unitarios (sin red):

```bash
pip install -e .[dev]
pytest tests/ -q
```

## Configuración en Claude Desktop

Copia el bloque de `claude_desktop_config.example.json` en tu `claude_desktop_config.json` (`%APPDATA%\Claude\`) y ajusta rutas y variables. Reinicia Claude Desktop.

Variables de entorno:

| Variable | Uso |
|---|---|
| `MERCADONA_POSTAL_CODE` | CP de entrega por defecto |
| `MERCADONA_WAREHOUSE` | Almacén (`mad1`, `vlc1`, `bcn1`...); se recalcula con `set_postal_code` |
| `MERCADONA_EMAIL` / `MERCADONA_PASSWORD` | Credenciales para `login` (recomendado frente a pasarlas por chat) |
| `MERCADONA_AUTH_SCHEME` | Esquema del header Authorization (`Bearer` por defecto; prueba `Token` o vacío si el login falla) |
| `MERCADONA_MIN_ORDER_EUR` | Pedido mínimo verificado antes del pago (60 por defecto) |
| `MERCADONA_ENABLE_CHECKOUT` | Debe valer `1`/`true` para que `place_order` pueda ejecutarse (desactivado por defecto) |
| `MERCADONA_PREFS_FILE` | Ruta del JSON de preferencias (`~/.mercadona_mcp_prefs.json` por defecto) |

## Tools

Catálogo (sin cuenta): `set_postal_code`, `search_products`, `get_categories`, `get_category_products`, `get_product`, `get_similar_products`, `get_new_arrivals`, `get_price_drops`.

`search_products` admite `sort` y `brand`: `sort="reference_price"` ordena por precio al kg/L (el modo de ahorro; comprueba `reference_format` si la búsqueda mezcla kg y L), `sort="unit_price"` por precio del envase, y `sort="relevance"` (por defecto) mantiene el orden del buscador. `brand="Hacendado"` filtra por marca exacta. Al ordenar o filtrar se recuperan 50 candidatos antes de recortar a `limit`, para no perder opciones baratas mal posicionadas. `limit` se acota a 100 internamente, para no poder forzar peticiones desproporcionadas a Algolia.

Cuenta (requiere `login`): `get_cart`, `add_to_cart`, `remove_from_cart`, `get_orders`, `get_addresses`, `get_payment_cards`.

Pago: `place_order` ejecuta un pago real e irreversible con la tarjeta guardada. Tiene tres salvaguardas: está **desactivado por defecto** y no se ejecuta nada hasta que fijes `MERCADONA_ENABLE_CHECKOUT=1` en el entorno del servidor (pensado para que conectar el MCP a un cliente/agente no habilite pagos por accidente, sobre todo en clientes que autoejecutan tools sin pedir confirmación humana); solo funciona con `confirm="CONFIRMO EL PAGO"` (pensado para que la IA lo pida tras mostrarte el carrito y el total); y antes de llamar al checkout verifica que el carrito alcanza el pedido mínimo de Mercadona — 60 €, configurable con `MERCADONA_MIN_ORDER_EUR` — abortando con el importe que falta si no llega.

Preferencias: `get_preferences`, `set_preference`, `delete_preference` mantienen un perfil de compra persistente entre sesiones (huevos camperos o libres de jaula, leche semidesnatada, prioridad al €/kg, marcas, etiqueta eco...). Las descripciones de las tools instruyen al modelo para consultarlo antes de elegir productos y para guardar proactivamente cualquier preferencia que expreses o corrección que hagas, de modo que la IA se adapta a ti y deja de preguntar lo mismo en cada compra. Se almacena en `~/.mercadona_mcp_prefs.json` (configurable con `MERCADONA_PREFS_FILE`) como clave-valor en texto claro, editable a mano.

Depuración: `raw_api_request` lanza peticiones arbitrarias a `/api` para adaptar los endpoints privados si Mercadona los cambia (los de carrito/checkout son los menos estables). Solo acepta rutas relativas dentro de `/api` (sin esquema, sin host, sin `..`); rechaza URLs absolutas para que el token de sesión no pueda acabar viajando a un host ajeno. Devuelve la respuesta de Mercadona sin filtrar: si el endpoint que pruebas expone datos sensibles (direcciones, tarjetas, tokens), saldrán tal cual en el resultado — no pegues esa salida en transcripciones o issues públicos.

## Ejemplo de uso en Claude

> "Busca leche entera y añade 6 bricks de la más barata al carrito"

Claude encadenará `search_products("leche entera", sort="reference_price")` → `login()` → `add_to_cart(id, 6)` → `get_cart()` para enseñarte el resultado.

## Estructura

```
mercadona_mcp/
  client.py    Cliente httpx (catálogo, Algolia, cuenta, checkout)
  prefs.py     Preferencias persistentes del usuario (JSON, escritura atómica)
  server.py    Tools MCP (FastMCP, stdio)
tests/         Tests con httpx.MockTransport y tmp_path
smoke_test.py  Verificación en vivo de endpoints públicos
register.py    Registro seguro del servidor en claude_desktop_config.json
API_STUDY.md   Estudio de la API (endpoints, incertidumbres, fuentes)
SECURITY.md    Modelo de amenaza y cómo reportar un problema de seguridad
.github/       CI (pytest en cada push/PR) y Dependabot (pip + Actions)
```
