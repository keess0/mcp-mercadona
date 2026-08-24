"""Preferencias persistentes del usuario para compras.

Almacen clave-valor en JSON (por defecto ~/.mercadona_mcp_prefs.json,
configurable con MERCADONA_PREFS_FILE). Las claves son categorias en texto
libre ("huevos", "leche", "marca") y los valores la preferencia expresada
por el usuario ("camperos; nunca de jaula"). Escritura atomica.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from typing import Optional


def _default_path() -> str:
    return os.getenv(
        "MERCADONA_PREFS_FILE",
        os.path.join(os.path.expanduser("~"), ".mercadona_mcp_prefs.json"),
    )


class Preferences:
    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path or _default_path()

    def _load(self) -> dict:
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self, data: dict) -> None:
        directory = os.path.dirname(self.path) or "."
        fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
        except BaseException:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise

    def get_all(self) -> dict:
        return {k: v.get("value") for k, v in self._load().items()}

    def set(self, key: str, value: str) -> dict:
        key = key.strip().lower()
        if not key:
            raise ValueError("La clave de preferencia no puede estar vacia.")
        data = self._load()
        data[key] = {"value": value.strip(), "updated_at": time.strftime("%Y-%m-%d")}
        self._save(data)
        return {"saved": {key: value.strip()}, "total": len(data)}

    def delete(self, key: str) -> dict:
        key = key.strip().lower()
        data = self._load()
        removed = data.pop(key, None) is not None
        if removed:
            self._save(data)
        return {"deleted": removed, "key": key}
