# C:\Users\gcave\Desktop\ColectorAW\src\awcollector\app.py
from __future__ import annotations

def main():
    # Import absoluto para que funcione al empaquetar con PyInstaller
    from awcollector.ui_tk import run
    run()

if __name__ == "__main__":
    main()
