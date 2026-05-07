from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui


@dataclass(frozen=True)
class AppShellConfig:
    """Shared shell configuration for Tk root windows."""

    title: str
    geometry: str
    min_width: int
    min_height: int


class TkinterAppShell:
    """Applies common window setup and close lifecycle handling."""

    def __init__(
        self,
        root: ui.Tk,
        config: AppShellConfig,
        *,
        on_close: Callable[[], bool | None] | None = None,
    ) -> None:
        self.root = root
        self.config = config
        self._on_close = on_close

        self.root.title(config.title)
        self.root.geometry(config.geometry)
        self.root.minsize(config.min_width, config.min_height)
        self.root.protocol("WM_DELETE_WINDOW", self._handle_close)

    def _handle_close(self) -> None:
        if self._on_close is not None:
            should_close = self._on_close()
            if should_close is False:
                return
        self.root.destroy()
