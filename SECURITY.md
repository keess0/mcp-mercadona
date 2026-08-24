# Seguridad

Este proyecto habla con una API **no oficial** de `tienda.mercadona.es` obtenida
por ingeniería inversa (ver [API_STUDY.md](API_STUDY.md)). Mercadona no
participa ni respalda este software; su uso automatizado puede incumplir sus
ToS. Úsalo bajo tu propia responsabilidad.

## Modelo de amenaza

El riesgo principal no es de terceros contra el servidor (no expone puertos
ni servicios: corre en local vía stdio, invocado por tu cliente MCP), sino:

- **Credenciales de tu cuenta de Mercadona** (`MERCADONA_EMAIL`/`PASSWORD`) y
  el token de sesión que obtiene `login()`, que viven solo en memoria del
  proceso mientras corre.
- **Pagos reales e irreversibles** vía `place_order`, que está desactivado
  por defecto (`MERCADONA_ENABLE_CHECKOUT`) y exige una frase de confirmación
  explícita además del mínimo de pedido.
- **`raw_api_request`**, pensada para depurar endpoints privados: solo acepta
  rutas relativas dentro de `/api` (rechaza URLs absolutas y `..`) para que
  el token de sesión no pueda acabar enviándose a un host ajeno, y devuelve
  la respuesta de Mercadona sin filtrar — no compartas esa salida si el
  endpoint que pruebas expone datos sensibles.

## Reportar un problema

Si encuentras un fallo de seguridad (fuga de credenciales, forma de saltarse
las salvaguardas de `place_order`, inyección en las peticiones a la API o a
Algolia, etc.), abre un issue privado o contacta directamente al mantenedor
en vez de abrir un issue público con detalles de explotación.

## Buenas prácticas al desplegarlo

Define `MERCADONA_EMAIL`/`MERCADONA_PASSWORD` como variables de entorno del
servidor, nunca las pases por chat. Mantén `MERCADONA_ENABLE_CHECKOUT` sin
definir (o en `0`) salvo que quieras pagos reales habilitados. Revisa
`~/.mercadona_mcp_prefs.json` de vez en cuando: es texto plano editable a
mano, no metas ahí nada más sensible que preferencias de compra.
