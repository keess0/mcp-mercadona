"""Tests del almacen de preferencias."""

import json
import os

import pytest

from mercadona_mcp.prefs import Preferences


def test_set_get_delete(tmp_path):
    p = Preferences(path=str(tmp_path / "prefs.json"))
    assert p.get_all() == {}

    out = p.set("Huevos", "camperos; nunca de jaula")
    assert out["saved"] == {"huevos": "camperos; nunca de jaula"}

    p.set("leche", "semidesnatada")
    assert p.get_all() == {
        "huevos": "camperos; nunca de jaula",
        "leche": "semidesnatada",
    }

    p.set("leche", "desnatada")
    assert p.get_all()["leche"] == "desnatada"

    assert p.delete("huevos") == {"deleted": True, "key": "huevos"}
    assert p.delete("huevos")["deleted"] is False
    assert p.get_all() == {"leche": "desnatada"}


def test_persistence_across_instances(tmp_path):
    path = str(tmp_path / "prefs.json")
    Preferences(path=path).set("eco", "preferir etiqueta eco si cuesta <10% mas")
    assert Preferences(path=path).get_all() == {
        "eco": "preferir etiqueta eco si cuesta <10% mas"
    }
    raw = json.load(open(path, encoding="utf-8"))
    assert "updated_at" in raw["eco"]


def test_corrupt_file_recovers(tmp_path):
    path = str(tmp_path / "prefs.json")
    with open(path, "w") as fh:
        fh.write("{no es json")
    p = Preferences(path=path)
    assert p.get_all() == {}
    p.set("marca", "Hacendado por defecto")
    assert p.get_all() == {"marca": "Hacendado por defecto"}


def test_empty_key_rejected(tmp_path):
    p = Preferences(path=str(tmp_path / "prefs.json"))
    with pytest.raises(ValueError):
        p.set("  ", "x")


def test_env_default_path(monkeypatch, tmp_path):
    target = str(tmp_path / "custom.json")
    monkeypatch.setenv("MERCADONA_PREFS_FILE", target)
    p = Preferences()
    p.set("pan", "integral")
    assert os.path.exists(target)
