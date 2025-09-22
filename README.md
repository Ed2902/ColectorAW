# ColectorAW

Utilidad para leer datos locales de ActivityWatch (http://localhost:5600) y enviarlos a un servidor central mediante un único botón **Enviar**.

## Requisitos
- Windows 11
- ActivityWatch en ejecución
- Python 3.11+ (solo para construir el .exe)

## Librerías
- httpx (HTTP moderno)
- tldextract (extraer dominio)
- tzlocal (zona horaria local)
- PyInstaller (empaquetado .exe)
- Tkinter (UI nativa incluida con Python)

## Estructura
- src/awcollector/app.py        (entrypoint)
- src/awcollector/ui_tk.py      (UI botón "Enviar")
- src/awcollector/aw_api.py     (API ActivityWatch)
- src/awcollector/aggregate.py  (agregado/resumen)
- src/awcollector/config.py     (carga settings)
- config/settings.json          (URL servidor y path ingest)
- scripts/build.ps1             (empaquetado .exe)
