# Estudio de la API de tienda.mercadona.es

Mercadona no publica una API oficial. Todo lo que sigue procede de ingeniería inversa del frontend (bundle JS `/v8451/index-*.js`), observación de tráfico y documentación de terceros, verificada por la comunidad en febrero de 2026. El backend parece Django REST Framework (las respuestas a `OPTIONS` exponen `name`, `renders`, `parses`, `actions`). `robots.txt` bloquea `/api`: el uso automatizado puede incumplir los ToS de Mercadona. Úsalo bajo tu responsabilidad y con rate limits razonables.

## Arquitectura

Dos sistemas independientes:

1. **API REST propia** — `https://tienda.mercadona.es/api/` para catálogo, cuenta, carrito y pedidos.
2. **Algolia** — búsqueda de texto libre contra `https://7uzjkl1dj0-dsn.algolia.net/1/indexes/products_prod_{wh}_es/query` con las claves públicas del frontend (app id `7UZJKL1DJ0`, api key `9d8f2e39e90df472b4f2e559a116fe17`). El índice depende del almacén: `products_prod_vlc1_es`, `products_prod_mad1_es`, etc. Algolia solo devuelve orden por relevancia; la ordenación por precio (`sort=reference_price|unit_price`) y el filtro `brand` se aplican en el cliente sobre un pool ampliado de 50 hits.

## Parámetros y headers comunes

`lang` (es/en) y `wh` (almacén: `mad1`, `vlc1`, `bcn1`, `alc1`...) como query params. El frontend manda además `x-version`, `x-customer-device-id` (UUID) y a veces `x-experiment-variants`; para lectura no son obligatorios. El almacén se deriva del código postal vía `PUT /api/postal-codes/actions/change-pc/` con `{"new_postal_code":"46001"}` — la respuesta trae `x-customer-pc` y `x-customer-wh`. Precios y surtido varían por almacén.

## Endpoints públicos (sin auth)

| Endpoint | Método | Notas |
|---|---|---|
| `/api/categories/` | GET | Árbol de categorías (2 niveles) |
| `/api/categories/{id}/` | GET | Categoría con sus productos (única forma de listar productos) |
| `/api/products/{id}/` | GET | Ficha completa; cache público 1800 s |
| `/api/products/{id}/similars/` | GET | Similares |
| `/api/products/{id}/xselling/` | GET | Venta cruzada |
| `/api/home/`, `/api/home/new-arrivals/`, `/api/home/price-drops/` | GET | Secciones del inicio |
| `/api/postal-codes/actions/change-pc/` | PUT | Fija CP y almacén |

`/api/products/` (listado global) devuelve 404: el catálogo completo se obtiene recorriendo categorías. Existe también una versión `/api/v1_1/` equivalente para categorías y productos.

## Endpoints privados (requieren token) — verificados en vivo (julio 2026)

### Autenticación: JWT en dos pasos sobre un único endpoint

`POST /api/auth/tokens/` acepta dos payloads alternativos (confirmado vía `OPTIONS`, que expone los campos `username`, `password` y `refresh_token`):

1. `{"username", "password"}` → respuesta con `customer_id` (UUID) y `refresh_token` (JWT SimpleJWT, `token_type: refresh`, caducidad larga). Según el estado de la cuenta puede incluir también el access token directamente.
2. `{"refresh_token": ...}` → devuelve `access_token` (y rotación opcional del `refresh_token`).

El access token va como `Authorization: Bearer <token>` (esquema configurable con `MERCADONA_AUTH_SCHEME`). `client.py` implementa el flujo completo: si el login solo devuelve `refresh_token`, lo intercambia automáticamente, y ante un 401 en cualquier llamada autenticada refresca y reintenta una vez. No hay endpoint `/auth/tokens/refresh/` separado (404).

### Carrito y cuenta — verificados contra cuenta real

- `GET /api/customers/{uuid}/cart/` → `{id, version, lines[], summary.total, products_count}`. El recurso está versionado (`version` incrementa con cada escritura).
- `PUT /api/customers/{uuid}/cart/` con `{"lines": [{"product_id", "quantity"}]}` → reemplaza el carrito completo; la respuesta incluye cada línea con la ficha del producto embebida. Verificado añadiendo y quitando productos reales.
- `GET /api/customers/{uuid}/orders/` → paginado `{next_page, results[]}`. Verificado.
- `GET /api/customers/{uuid}/addresses/` y `/payment-cards/` → paginado DRF `{count, next, previous, results[]}`. Verificados.

**Pendiente de verificar**: `POST /api/customers/{uuid}/orders/` (checkout). Implementado con payload `{slot_id, address_id, payment_card_id}` como mejor reconstrucción; requiere cuenta con dirección y tarjeta guardadas. `raw_api_request` permite ajustar el payload observando DevTools si difiere.

## Estructura de precios

Cada producto lleva `price_instructions`: `unit_price` (EUR por unidad de venta), `reference_price` + `reference_format` (EUR/kg o EUR/L), `unit_size`, `iva`, `is_pack`, `bulk_price`, flags `is_new` y `price_decreased`.

## Decisiones de diseño del servidor MCP

**Preferencias del usuario**: el servidor mantiene un almacén clave-valor persistente (`prefs.py`, JSON con escritura atómica) para preferencias de compra: tipo de huevos, leche, criterio de precio, marcas, eco. No es parte de la API de Mercadona — es estado local del MCP. El mecanismo de adaptación está en las descripciones de las tools: `get_preferences` ordena al modelo consultarlas antes de elegir productos, y `set_preference` le indica guardar proactivamente lo que el usuario exprese o corrija. Así el aprendizaje sobrevive entre sesiones y entre modelos distintos sin depender de la memoria del cliente.

Credenciales por variables de entorno (no viajan por el chat ni quedan en logs de conversación). El pago (`place_order`) tiene dos salvaguardas: exige el literal `confirm="CONFIRMO EL PAGO"`, pensado para que el modelo solo lo emita tras aprobación explícita del usuario con el total a la vista, y verifica contra el carrito real que se alcanza el pedido mínimo de Mercadona (60 €, `MERCADONA_MIN_ORDER_EUR`) antes de tocar el endpoint de checkout. Las respuestas de catálogo se compactan (id, nombre, marca, precios) para no quemar contexto; la ficha completa queda en `get_product`. Tokens (access y refresh) solo en memoria del proceso, nunca persistidos.

## Fuentes

- [datania/mercadona-catalog api.md](https://github.com/datania/mercadona-catalog/blob/main/api.md)
- [Trasteando la API del Mercadona (Antonio Blanco, Medium)](https://medium.com/@ablancodev/trasteando-la-api-del-mercadona-cff067abc002)
- [Gist de mdelapenya con la query Algolia](https://gist.github.com/mdelapenya/7a7bf8e6f22d86d28ad3b5e3630b1343)
- [m0wer/mercaapi](https://github.com/m0wer/mercaapi)
