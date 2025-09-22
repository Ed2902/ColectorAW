# C:\Users\gcave\Desktop\ColectorAW\src\awcollector\ui_tk.py
from __future__ import annotations
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import os, sys
from pathlib import Path
from typing import Callable

# --- Logo .webp ---
try:
    from PIL import Image, ImageTk  # requiere pillow
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False

from .config import load_settings, PENDING_DIR
from .aggregate import build_daily_payload, send_payload, resend_pending

# ---------- Paleta Genika ----------
COLOR_BG      = "#FFFFFF"   # Blanco
COLOR_TEXT    = "#0B3D6E"   # Azul profundo
COLOR_ACCENT  = "#2CB6C0"   # Turquesa
COLOR_ORANGE  = "#FF7A00"   # Naranja
COLOR_GREEN   = "#2BB673"   # Verde
COLOR_MUTED   = "#6B7280"   # Gris texto
COLOR_DIVIDER = "#E5E7EB"   # Divisor

# Ruta segura a assets (funciona en .py y en .exe)
def _resource_path(rel: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))  # repo root en dev
    return base / rel

def _open_folder(path: Path):
    try:
        os.startfile(str(path))
    except Exception as e:
        messagebox.showerror("Genika Control", f"No se pudo abrir la carpeta:\n{e}")

# ---------- Botón redondeado en Canvas ----------
class RoundedButton(tk.Canvas):
    def __init__(
        self,
        master,
        text: str,
        command: Callable[[], None],
        width: int = 230,
        height: int = 46,
        radius: int = 18,
        bg=COLOR_BG,
        fill=COLOR_ACCENT,
        hover_fill=COLOR_GREEN,
        font=("Segoe UI", 10, "bold"),
        **kwargs
    ):
        super().__init__(master, width=width, height=height, highlightthickness=0, bg=bg, **kwargs)
        self._command = command
        self._fill = fill
        self._hover_fill = hover_fill
        self._font = font
        self._rect = self._rounded_rect(2, 2, width-2, height-2, radius, fill)
        self._label = self.create_text(width//2, height//2, text=text, fill="#FFFFFF", font=self._font)
        self.bind("<Enter>", lambda e: self.itemconfig(self._rect, fill=self._hover_fill))
        self.bind("<Leave>", lambda e: self.itemconfig(self._rect, fill=self._fill))
        self.bind("<Button-1>", lambda e: self._command() if callable(self._command) else None)
        self.bind("<Key-Return>", lambda e: self._command() if callable(self._command) else None)
        self.configure(cursor="hand2")

    def _rounded_rect(self, x1, y1, x2, y2, r, color):
        pts = [
            (x1+r, y1, x2-r, y1), (x2-r, y1, x2, y1+r), (x2, y1+r, x2, y2-r),
            (x2, y2-r, x2-r, y2), (x2-r, y2, x1+r, y2), (x1+r, y2, x1, y2-r),
            (x1, y2-r, x1, y1+r), (x1, y1+r, x1+r, y1),
        ]
        return self.create_polygon([c for p in pts for c in p], smooth=True, fill=color, outline="")

class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Genika Control")

        # === Icono de la ventana (usa assets/Genika.ico) ===
        icon_path = _resource_path(r"assets/Genika.ico")
        if icon_path.exists():
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass
        # ===================================================

        self.geometry("520x300")
        self.resizable(False, False)
        self.configure(bg=COLOR_BG)

        # Fuente global (usa tupla para evitar el error "UI")
        try:
            self.option_add("*Font", ("Segoe UI", 10))
        except Exception:
            pass

        # Estilos ttk
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Genika.TFrame", background=COLOR_BG)
        style.configure("Genika.Title.TLabel", background=COLOR_BG, foreground=COLOR_TEXT, font=("Segoe UI", 12, "bold"))
        style.configure("Genika.SubLabel.TLabel", background=COLOR_BG, foreground=COLOR_MUTED, font=("Segoe UI", 9))
        style.configure("Genika.TSeparator", background=COLOR_DIVIDER)
        style.configure("Genika.TButton", font=("Segoe UI", 10), padding=6)

        # Contenedor
        frm = ttk.Frame(self, padding=16, style="Genika.TFrame")
        frm.pack(fill="both", expand=True)

        # ---- Logo ----
        self._logo_img = None
        logo_path = _resource_path(r"assets/Genika.webp")
        if _HAS_PIL and logo_path.exists():
            img = Image.open(logo_path).convert("RGBA")
            base_h = 48
            w, h = img.size
            img = img.resize((int(w * (base_h / h)), base_h), Image.LANCZOS)
            self._logo_img = ImageTk.PhotoImage(img)
            tk.Label(frm, image=self._logo_img, bg=COLOR_BG).pack(anchor="w", pady=(0,6))

        # Título y divisor
        ttk.Label(frm, text="Genika Control", style="Genika.Title.TLabel").pack(anchor="w")
        ttk.Separator(frm, style="Genika.TSeparator").pack(fill="x", pady=8)

        # Subtítulo
        ttk.Label(frm, text="Resumen diario de ActivityWatch", style="Genika.SubLabel.TLabel").pack(anchor="w", pady=(0,6))

        # ---- Botones fila ----
        row = ttk.Frame(frm, style="Genika.TFrame")
        row.pack(pady=6, fill="x")

        self.round_send = RoundedButton(
            row,
            text="Enviar mi actividad",
            command=self.on_send_click,
            width=230,
            height=46,
            radius=18,
            bg=COLOR_BG,
            fill=COLOR_ACCENT,
            hover_fill=COLOR_GREEN,
            font=("Segoe UI", 10, "bold"),
        )
        self.round_send.pack(side="left", padx=(0,12))

        self.btn_retry = ttk.Button(row, text="Reintentar pendientes", style="Genika.TButton", command=self.on_retry_click)
        self.btn_retry.pack(side="left", padx=(0,8))

        self.btn_open_pending = ttk.Button(row, text="Abrir pending", style="Genika.TButton",
                                           command=lambda: _open_folder(PENDING_DIR))
        self.btn_open_pending.pack(side="left")

        # Estado
        self.status = tk.StringVar(value="Listo.")
        ttk.Label(frm, textvariable=self.status, style="Genika.SubLabel.TLabel", wraplength=480).pack(anchor="w", pady=10)

        # Pie de ayuda
        ttk.Label(frm, text="Asegúrate que ActivityWatch esté corriendo (http://localhost:5600).",
                  style="Genika.SubLabel.TLabel").pack(anchor="w", pady=(6,0))

        self.settings = load_settings()


    # --- Enviar ---
    def on_send_click(self):
        self._set_busy(True, "Generando resumen…")
        threading.Thread(target=self._do_send, daemon=True).start()

    def _do_send(self):
        try:
            payload = build_daily_payload(self.settings)
            self.status.set("Enviando al servidor…")
            ok, msg = send_payload(self.settings, payload)
            self.status.set(msg)
            if ok:
                messagebox.showinfo("Genika Control", "✅ Datos enviados con éxito.")
            else:
                messagebox.showwarning("Genika Control", f"❕ {msg}")
        except Exception as e:
            self.status.set(f"Error: {e}")
            messagebox.showerror("Genika Control", f"❌ Error inesperado:\n{e}")
        finally:
            self._set_busy(False)

    # --- Reintentar pendientes ---
    def on_retry_click(self):
        self._set_busy(True, "Reintentando envíos pendientes…")
        threading.Thread(target=self._do_retry, daemon=True).start()

    def _do_retry(self):
        try:
            results = resend_pending(self.settings)
            if not results:
                self.status.set("No hay archivos pendientes.")
                messagebox.showinfo("Genika Control", "No hay archivos pendientes.")
                return
            ok_count = sum(1 for _, ok, _ in results if ok)
            fail_count = len(results) - ok_count
            self.status.set(f"Reintento terminado. OK: {ok_count}, Fallidos: {fail_count}")
            if fail_count == 0:
                messagebox.showinfo("Genika Control", f"✅ Reintento exitoso. Enviados: {ok_count}")
            else:
                messagebox.showwarning("Genika Control", f"Parcial. Enviados: {ok_count}, Fallidos: {fail_count}\n(Revisa la carpeta pending)")
        except Exception as e:
            self.status.set(f"Error al reintentar: {e}")
            messagebox.showerror("Genika Control", f"❌ Error al reintentar:\n{e}")
        finally:
            self._set_busy(False)

    # --- util ---
    def _set_busy(self, busy: bool, msg: str | None = None):
        self.round_send.configure(cursor="watch" if busy else "hand2")
        state = "disabled" if busy else "normal"
        self.btn_retry.config(state=state)
        self.btn_open_pending.config(state=state)
        if msg:
            self.status.set(msg)

def run():
    app = App()
    app.mainloop()
