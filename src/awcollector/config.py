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

# ➕ Pendientes específicos para fotos (JSON + copias de archivos)
PENDING_PHOTOS_DIR = PENDING_DIR / "photos"
PENDING_PHOTOS_FILES_DIR = PENDING_PHOTOS_DIR / "files"

DEFAULTS = {
    # === API de reportes (ActivityWatch) ===
    "server_url": "https://aw.appfastway.com",
    "ingest_path": "/reports",
    "aw_base_url": "http://localhost:5600/api/0",
    "request_timeout_sec": 20,
    "top_titles_limit": 5,
    "top_urls_limit": 5,

    # === API de marcación con foto ===
    # Base provista por ti; no requiere token
    "photo_api_url": "https://app.appfastway.com",
    # Endpoint real donde tu front envía multipart con tipo/file/umbral
    "photo_ingest_path": "/app/marcacion/auto",
    # Nombre del campo archivo en multipart
    "photo_field_file": "file",
    # Validaciones básicas
    "photo_allowed_ext": ["jpg", "jpeg", "png", "webp"],
    "photo_max_mb": 8,
    # Parámetros adicionales (por defecto igual que en el front)
    "photo_default_umbral": 0.55,
    # (Opcional) token si algún día lo necesitas; hoy se deja vacío
    "photo_auth_token": "",
}

def ensure_dirs() -> None:
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    # ➕ aseguramos carpetas de fotos pendientes
    PENDING_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    PENDING_PHOTOS_FILES_DIR.mkdir(parents=True, exist_ok=True)

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

    # === Normalizaciones de URLs/paths ===
    # Reportes
    cfg["server_url"] = str(cfg["server_url"]).rstrip("/")
    cfg["ingest_path"] = "/" + str(cfg["ingest_path"]).lstrip("/")
    cfg["aw_base_url"] = str(cfg["aw_base_url"]).rstrip("/")

    # Fotos
    cfg["photo_api_url"] = str(cfg.get("photo_api_url", "")).rstrip("/")
    cfg["photo_ingest_path"] = "/" + str(cfg.get("photo_ingest_path", "")).lstrip("/")
    # Coherencia de tipos
    try:
        cfg["photo_max_mb"] = float(cfg.get("photo_max_mb", 8))
    except Exception:
        cfg["photo_max_mb"] = 8.0
    try:
        cfg["photo_default_umbral"] = float(cfg.get("photo_default_umbral", 0.55))
    except Exception:
        cfg["photo_default_umbral"] = 0.55

    return cfg
