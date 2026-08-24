"""Registra el servidor mercadona en claude_desktop_config.json sin tocar nada mas.

Uso:  python register.py

Garantias:
  - Solo modifica la clave mcpServers.mercadona; el resto queda byte a byte igual
    salvo re-indentado uniforme a 2 espacios.
  - Backup con timestamp antes de escribir.
  - Valida el JSON antes y despues; si algo no cuadra, aborta sin escribir.
  - Escribe UTF-8 sin BOM (el BOM de PowerShell rompe el parser de Claude).
"""

import json
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))

SERVER = {
    "command": sys.executable,
    "args": ["-m", "mercadona_mcp.server"],
    "env": {
        "PYTHONPATH": ROOT,
        "MERCADONA_POSTAL_CODE": "28001",
    },
}


def candidate_dirs():
    dirs = [os.path.expandvars(r"%APPDATA%\Claude")]
    packages = os.path.expandvars(r"%LOCALAPPDATA%\Packages")
    if os.path.isdir(packages):
        for name in os.listdir(packages):
            if name.startswith("Claude_"):
                dirs.append(os.path.join(packages, name, "LocalCache", "Roaming", "Claude"))
    return [d for d in dirs if os.path.isdir(d)]


def register(config_path: str) -> None:
    if os.path.exists(config_path):
        with open(config_path, encoding="utf-8-sig") as fh:
            config = json.load(fh)
        if not isinstance(config, dict):
            raise ValueError(f"{config_path}: la raiz no es un objeto JSON")
        backup = f"{config_path}.{time.strftime('%Y%m%d-%H%M%S')}.bak"
        shutil.copy2(config_path, backup)
        print(f"  backup -> {backup}")
    else:
        config = {}

    existing = config.get("mcpServers")
    if existing is None:
        config["mcpServers"] = {}
    elif not isinstance(existing, dict):
        raise ValueError(f"{config_path}: mcpServers no es un objeto, no toco nada")

    previous = config["mcpServers"].get("mercadona", {})
    merged_env = dict(SERVER["env"])
    if isinstance(previous, dict):
        merged_env.update(previous.get("env", {}) or {})
    merged_env["PYTHONPATH"] = ROOT
    entry = dict(SERVER)
    entry["env"] = merged_env
    config["mcpServers"]["mercadona"] = entry

    text = json.dumps(config, indent=2, ensure_ascii=False) + "\n"
    json.loads(text)
    with open(config_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print(f"  OK, servidores: {sorted(config['mcpServers'])}")


def main() -> None:
    dirs = candidate_dirs()
    if not dirs:
        sys.exit("No se encontro ninguna carpeta de configuracion de Claude.")
    for d in dirs:
        path = os.path.join(d, "claude_desktop_config.json")
        print(f"* {path}")
        register(path)
    print("\nHecho. Reinicia Claude Desktop (tambien desde la bandeja del sistema).")


if __name__ == "__main__":
    main()
