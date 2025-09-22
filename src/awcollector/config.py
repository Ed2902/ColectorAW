# C:\Users\gcave\Desktop\ColectorAW\src\awcollector\config.py
from __future__ import annotations
from pathlib import Path
import json
import os

# Raíz del repo = 3 niveles arriba de este archivo
ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
SETTINGS_FILE = CONFIG_DIR / "settings.json"

# Directorios de datos locales en AppData\Local\ColectorAW
APPDATA = Path(os.environ.get("LOCALAPPDATA", str(ROOT))) / "ColectorAW"
PENDING_DIR = APPDATA / "pending"
LOGS_DIR = APPDATA / "logs"
 
DEFAULTS = {
    "server_url": "https://aw.appfastway.com",
    "ingest_path": "/reports",
    "aw_base_url": "http://localhost:5600/api/0",
    "request_timeout_sec": 20,
    "top_titles_limit": 5,
    "top_urls_limit": 5,
}

def ensure_dirs() -> None:
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

def load_settings() -> dict:
    """Carga settings.json y aplica defaults."""
    ensure_dirs()
    data = {}
    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            # si hay error leyendo JSON, seguimos con defaults
            data = {}
    cfg = {**DEFAULTS, **(data or {})}
    # normalizar path de servidor (sin slash final)
    cfg["server_url"] = str(cfg["server_url"]).rstrip("/")
    cfg["ingest_path"] = "/" + str(cfg["ingest_path"]).lstrip("/")
    cfg["aw_base_url"] = str(cfg["aw_base_url"]).rstrip("/")
    return cfg
