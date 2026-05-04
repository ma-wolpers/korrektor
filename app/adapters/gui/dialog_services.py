from __future__ import annotations

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()

from bw_gui.dialogs import FileDialogService, MessageDialogService, TextPromptDialogService


messagebox = MessageDialogService()
simpledialog = TextPromptDialogService()
filedialog = FileDialogService()
