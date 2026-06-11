"""
Image preview overlay — fit-to-window preview of an image file inside a
mod, including .dds textures (Pillow's DDS decoder handles DXT1/3/5 and
the BC formats). Alpha is composited onto a checkerboard.

Place over the modlist panel via place(relx=0, rely=0, relwidth=1,
relheight=1). The caller owns opening/closing; call ``show(path)`` to
swap the displayed file in place. Decoding runs on a background thread
so a 4K BC7 texture doesn't stall the UI.
"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from typing import Callable

import customtkinter as ctk
from PIL import Image as PilImage, ImageDraw, ImageTk

from gui.theme import (
    BG_DEEP,
    BG_HEADER,
    FONT_BOLD,
    TEXT_DIM,
    TEXT_MAIN,
    TK_FONT_BOLD,
    TK_FONT_SMALL,
)

# Extensions the Mod Files tab offers a preview for. Everything here is
# decodable by the bundled Pillow (DDS support depends on the texture's
# compression — unsupported variants surface a decode-error message).
PREVIEW_EXTS = {
    ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp",
    ".tga", ".tif", ".tiff", ".ico", ".dds",
}

_RESAMPLE = (
    PilImage.Resampling.LANCZOS
    if hasattr(PilImage, "Resampling") else PilImage.LANCZOS  # type: ignore
)


def _checkerboard(w: int, h: int) -> PilImage.Image:
    """Dark checkerboard backdrop so transparency is visible."""
    tile = 12
    pattern = PilImage.new("RGB", (tile * 2, tile * 2), "#353535")
    d = ImageDraw.Draw(pattern)
    d.rectangle((0, 0, tile - 1, tile - 1), fill="#454545")
    d.rectangle((tile, tile, tile * 2 - 1, tile * 2 - 1), fill="#454545")
    board = PilImage.new("RGB", (w, h))
    for y in range(0, h, tile * 2):
        for x in range(0, w, tile * 2):
            board.paste(pattern, (x, y))
    return board.convert("RGBA")


class ImagePreviewOverlay(tk.Frame):
    """Single-image lightbox with a title/info toolbar and Close button."""

    def __init__(self, parent: tk.Widget, *, on_close: Callable[[], None]):
        super().__init__(parent, bg=BG_DEEP)
        self._on_close = on_close
        self._src_image: PilImage.Image | None = None
        self._error: str | None = None
        self._photo: ImageTk.PhotoImage | None = None
        self._load_gen = 0
        self._resize_after_id: str | None = None

        toolbar = tk.Frame(self, bg=BG_HEADER)
        toolbar.pack(side="top", fill="x")
        toolbar.grid_columnconfigure(0, weight=1)

        self._title_label = tk.Label(
            toolbar, text="", font=TK_FONT_BOLD, fg=TEXT_MAIN, bg=BG_HEADER,
            anchor="w", justify="left",
        )
        self._title_label.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 0))

        self._info_label = tk.Label(
            toolbar, text="", font=TK_FONT_SMALL, fg=TEXT_DIM, bg=BG_HEADER,
            anchor="w", justify="left",
        )
        self._info_label.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))

        ctk.CTkButton(
            toolbar, text="✕ Close", width=85, height=30,
            fg_color="#6b3333", hover_color="#8c4444", text_color="white",
            font=FONT_BOLD, command=self._handle_close,
        ).grid(row=0, column=1, rowspan=2, sticky="e", padx=(6, 12), pady=8)

        self._canvas = tk.Canvas(self, bg=BG_DEEP, highlightthickness=0, bd=0)
        self._canvas.pack(side="top", fill="both", expand=True)
        self._canvas.bind("<Configure>", self._on_canvas_resize)

        self.bind("<Escape>", lambda e: self._handle_close())
        self.focus_set()

    def _handle_close(self) -> None:
        self._on_close()

    # ------------------------------------------------------------------

    def show(self, path: Path) -> None:
        """Load *path* on a worker thread and display it when ready."""
        self._load_gen += 1
        gen = self._load_gen
        self._title_label.configure(text=Path(path).name)
        self._info_label.configure(text="loading…")
        threading.Thread(
            target=self._load_worker, args=(Path(path), gen), daemon=True,
        ).start()

    def _load_worker(self, path: Path, gen: int) -> None:
        img: PilImage.Image | None = None
        info = ""
        err: str | None = None
        try:
            img = PilImage.open(path)
            img.load()
            fmt = img.format or path.suffix.lstrip(".").upper()
            info = f"{img.width} × {img.height} — {fmt}"
            pixel_format = img.info.get("pixel_format")
            if pixel_format:
                info += f" ({pixel_format})"
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA")
        except Exception as exc:
            img = None
            err = str(exc) or exc.__class__.__name__

        def _apply():
            if gen != self._load_gen:
                return  # superseded by a newer show()
            try:
                if not self.winfo_exists():
                    return
                self._src_image = img
                self._error = err
                self._info_label.configure(
                    text="(could not decode)" if err else info,
                )
                self._render()
            except tk.TclError:
                pass  # overlay closed while decoding

        try:
            self.after(0, _apply)
        except Exception:
            pass  # overlay destroyed while decoding

    # ------------------------------------------------------------------

    def _on_canvas_resize(self, event: tk.Event) -> None:
        # Debounce — <Configure> fires repeatedly during a window drag.
        if self._resize_after_id is not None:
            try:
                self.after_cancel(self._resize_after_id)
            except Exception:
                pass
        self._resize_after_id = self.after(80, self._render)

    def _render(self) -> None:
        self._resize_after_id = None
        c = self._canvas
        try:
            if not c.winfo_exists():
                return
        except tk.TclError:
            return
        c.delete("all")
        cw = max(c.winfo_width(), 1)
        ch = max(c.winfo_height(), 1)
        if self._error is not None:
            c.create_text(
                cw // 2, ch // 2, text=f"Could not decode image:\n{self._error}",
                fill=TEXT_DIM, font=TK_FONT_SMALL, justify="center",
                width=max(cw - 32, 100),
            )
            return
        img = self._src_image
        if img is None or cw < 2 or ch < 2:
            return
        pad = 16
        scale = min((cw - pad) / img.width, (ch - pad) / img.height, 1.0)
        w = max(int(img.width * scale), 1)
        h = max(int(img.height * scale), 1)
        disp = img if (w, h) == img.size else img.resize((w, h), _RESAMPLE)
        if disp.mode == "RGBA":
            disp = PilImage.alpha_composite(_checkerboard(w, h), disp)
        self._photo = ImageTk.PhotoImage(disp)
        c.create_image(cw // 2, ch // 2, image=self._photo, anchor="center")
