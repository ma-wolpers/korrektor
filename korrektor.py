from __future__ import annotations

import sys

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()


def _show_start_error(message: str) -> None:
    """Show startup errors in dialog (pythonw) and console."""
    try:
        from bw_gui.dialogs import MessageDialogService

        MessageDialogService().showerror("Korrektor Startfehler", message)
    except Exception:
        pass
    print(message, file=sys.stderr)


def main() -> int:
    try:
        from app.app import run
    except ModuleNotFoundError as exc:
        missing_name = str(getattr(exc, "name", "") or "").strip() or "unbekannt"
        _show_start_error(
            "Korrektor konnte nicht gestartet werden, weil ein Python-Paket fehlt.\n\n"
            f"Fehlendes Paket: {missing_name}\n\n"
            "Bitte im Ordner Code/korrektor die Abhaengigkeiten installieren:\n"
            "1) .venv aktivieren\n"
            "2) pip install -r requirements.txt"
        )
        return 1

    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
