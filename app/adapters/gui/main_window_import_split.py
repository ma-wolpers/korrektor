from __future__ import annotations

from pathlib import Path

import fitz

from app.adapters.gui.dialog_services import filedialog, messagebox
from app.core.domain.pdf_split_planning import compute_split_ranges
from app.infrastructure.pdf.pdf_splitter import split_pdf_by_ranges

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui, widgets
from bw_gui.widgets import Checkbox


class MainWindowImportSplitMixin:
    """PDF-Import-Assistent (Korrektor-Wunschliste "Dateien"): eine grosse kombinierte PDF in einzelne Abgaben splitten.

    Läuft bewusst unabhängig von einer offenen Klausur - `CreateExamUseCase`/
    `PyMuPdfScanRepository.scan_exam_folder` setzen weiterhin einen Ordner
    mit bereits einzelnen PDFs voraus; dieser Assistent erzeugt genau so
    einen Ordner (sequentiell benannt, `Abgabe_01.pdf`, ...), die
    tatsächliche Namensvergabe pro Person passiert danach wie bisher über
    den bestehenden Namenmodus.

    Ein einfaches `ui.Toplevel` statt `ScrollablePopupWindow` (bewusste
    Ausnahme von der bw-gui-Standard-Scrollbarkeit, siehe
    `bw-gui/docs/SCROLLABILITY_CONTRACT.md`) - Präzedenz: der strukturell
    identische Extraseiten-Popup-Seitenviewer
    (`main_window_extra_pages.py`): ein grosser Canvas mit fester Seiten-
    Vorschau plus einer kleinen Bedienleiste ist derselbe "selbstständige
    Canvas-Anzeige, ein äusserer Scroll-Layer bietet keinen Mehrwert"-Fall.
    """

    def _open_import_split_wizard(self) -> None:
        source = filedialog.askopenfilename(
            title="Kombinierte PDF waehlen", filetypes=[("PDF-Dateien", "*.pdf")]
        )
        if not source:
            return
        source_path = Path(source)
        try:
            document = fitz.open(source_path)
        except Exception as exc:
            messagebox.showerror("Fehler", f"PDF konnte nicht geoeffnet werden: {exc}")
            return
        if document.page_count < 1:
            document.close()
            messagebox.showerror("Fehler", "Diese PDF hat keine Seiten.")
            return

        self._close_import_split_popup()
        self._import_split_document = document
        self._import_split_source_path = source_path
        self._import_split_page_index = 0
        self._import_split_boundary_pages = set()

        self._build_import_split_popup(source_path)
        self._render_import_split_page()

    def _build_import_split_popup(self, source_path: Path) -> None:
        popup = ui.Toplevel(self.root)
        popup.title(f"PDF importieren && aufteilen: {source_path.name}")
        popup.geometry("760x900")
        popup.minsize(640, 600)
        popup.transient(self.root)
        self._register_popup_window(popup)

        header = widgets.Frame(popup, padding=10)
        header.pack(fill=ui.X)
        self._import_split_info_var = ui.StringVar(value="")
        widgets.Label(header, textvariable=self._import_split_info_var, style="Muted.TLabel").pack(side=ui.LEFT)

        canvas_bg, canvas_border = self._canvas_theme_tokens()
        self._import_split_canvas = ui.Canvas(
            popup, bg=canvas_bg, highlightthickness=1, highlightbackground=canvas_border
        )
        self._import_split_canvas.pack(fill=ui.BOTH, expand=True, padx=10, pady=(0, 10))

        nav = widgets.Frame(popup, padding=(10, 0, 10, 6))
        nav.pack(fill=ui.X)
        prev_button = widgets.Button(
            nav, text="◀", style="SecondaryAction.TButton", command=lambda: self._change_import_split_page(-1)
        )
        prev_button.pack(side=ui.LEFT)
        self._attach_hover_help(prev_button, label="Vorherige Seite", shortcut="Links")
        next_button = widgets.Button(
            nav, text="▶", style="SecondaryAction.TButton", command=lambda: self._change_import_split_page(1)
        )
        next_button.pack(side=ui.LEFT, padx=(8, 0))
        self._attach_hover_help(next_button, label="Naechste Seite", shortcut="Rechts")

        self._import_split_boundary_var = ui.BooleanVar(value=True)
        # Checkbox: only collects boundaries locally; the split runs on "Aufteilen...".
        self._import_split_boundary_check = Checkbox(
            nav,
            text="Hier beginnt neue Abgabe",
            variable=self._import_split_boundary_var,
            on_select=lambda _selected: self._on_import_split_boundary_toggled(),
        )
        self._import_split_boundary_check.pack(side=ui.LEFT, padx=(16, 0))

        self._import_split_count_var = ui.StringVar(value="")
        widgets.Label(nav, textvariable=self._import_split_count_var, style="Status.TLabel").pack(
            side=ui.LEFT, padx=(16, 0)
        )

        actions = widgets.Frame(popup, padding=(10, 0, 10, 10))
        actions.pack(fill=ui.X)
        split_button = widgets.Button(
            actions, text="Aufteilen...", style="PrimaryAction.TButton", command=self._run_import_split
        )
        split_button.pack(side=ui.LEFT)
        close_button = widgets.Button(
            actions, text="Schliessen", style="SecondaryAction.TButton", command=self._close_import_split_popup
        )
        close_button.pack(side=ui.RIGHT)

        popup.protocol("WM_DELETE_WINDOW", self._close_import_split_popup)
        self._import_split_popup = popup

    def _change_import_split_page(self, delta: int) -> None:
        if self._import_split_document is None:
            return
        new_index = self._import_split_page_index + delta
        if not (0 <= new_index < self._import_split_document.page_count):
            return
        self._import_split_page_index = new_index
        self._render_import_split_page()

    def _on_import_split_boundary_toggled(self) -> None:
        """Add/remove the current page from the boundary set (page 1's checkbox is disabled, always on)."""
        if self._import_split_boundary_var is None:
            return
        page_number = self._import_split_page_index + 1
        if self._import_split_boundary_var.get():
            self._import_split_boundary_pages.add(page_number)
        else:
            self._import_split_boundary_pages.discard(page_number)
        self._update_import_split_count_label()

    def _render_import_split_page(self) -> None:
        if self._import_split_document is None or self._import_split_canvas is None:
            return
        page = self._import_split_document.load_page(self._import_split_page_index)
        target_width = 700.0
        scale = target_width / max(page.rect.width, 1.0)
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        self._import_split_photo = ui.PhotoImage(data=pix.tobytes("ppm"), format="ppm")
        self._import_split_canvas.delete("all")
        self._import_split_canvas.configure(width=pix.width, height=pix.height)
        self._import_split_canvas.create_image(0, 0, anchor=ui.NW, image=self._import_split_photo)

        page_number = self._import_split_page_index + 1
        is_boundary = page_number == 1 or page_number in self._import_split_boundary_pages
        if self._import_split_boundary_var is not None:
            self._import_split_boundary_var.set(is_boundary)
        if self._import_split_boundary_check is not None:
            # Seite 1 zaehlt immer implizit als erste Grenze (compute_split_ranges) -
            # die Checkbox zeigt das nur an, laesst sich fuer Seite 1 aber nicht abschalten.
            self._import_split_boundary_check.configure(state="disabled" if page_number == 1 else "normal")
        if self._import_split_info_var is not None:
            self._import_split_info_var.set(f"Seite {page_number}/{self._import_split_document.page_count}")
        self._update_import_split_count_label()

    def _update_import_split_count_label(self) -> None:
        if self._import_split_document is None or self._import_split_count_var is None:
            return
        ranges = compute_split_ranges(self._import_split_document.page_count, self._import_split_boundary_pages)
        self._import_split_count_var.set(f"{len(ranges)} Abgabe(n) erkannt")

    def _run_import_split(self) -> None:
        if self._import_split_document is None or self._import_split_source_path is None:
            return
        output_dir_raw = filedialog.askdirectory(title="Zielordner fuer die aufgeteilten PDFs waehlen")
        if not output_dir_raw:
            return
        ranges = compute_split_ranges(self._import_split_document.page_count, self._import_split_boundary_pages)
        try:
            created = split_pdf_by_ranges(self._import_split_source_path, ranges, Path(output_dir_raw))
        except FileExistsError as exc:
            messagebox.showerror("Aufteilen nicht moeglich", str(exc))
            return
        except Exception as exc:
            messagebox.showerror("Aufteilen fehlgeschlagen", str(exc))
            return
        messagebox.showinfo(
            "Aufteilen abgeschlossen",
            f"{len(created)} Datei(en) erstellt in:\n{output_dir_raw}\n\n"
            "Diesen Ordner kannst du jetzt ueber 'Neue Klausur anlegen' oeffnen und "
            "die Personen anschliessend im Namenmodus benennen.",
        )
        self._close_import_split_popup()

    def _close_import_split_popup(self) -> None:
        if self._import_split_popup is not None and self._import_split_popup.winfo_exists():
            popup_id = str(self._import_split_popup)
            self._popup_registry.close_popup(popup_id)
            self._tracked_popup_ids.discard(popup_id)
            self._import_split_popup.destroy()
        self._import_split_popup = None
        self._import_split_canvas = None
        self._import_split_info_var = None
        self._import_split_boundary_var = None
        self._import_split_boundary_check = None
        self._import_split_count_var = None
        if self._import_split_document is not None:
            try:
                self._import_split_document.close()
            except Exception:
                pass
        self._import_split_document = None
        self._import_split_source_path = None
        self._import_split_page_index = 0
        self._import_split_boundary_pages = set()
