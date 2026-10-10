"""REINE UEBERGANGSLOESUNG - nicht ausbauen, nicht wiederverwenden, nur loeschen.

BAUSTELLE: Dieses Modul existiert ausschliesslich, damit der Korrektor nach dem
Breaking Change in bw-gui 6d32767 (Keyboard-Contract auf ``KeySpec``) wieder startet.
Es uebersetzt die Tk-Sequenzen, die der Korrektor noch selbst per ``bind_all``
bindet, in ``KeySpec``s fuer ``KeyBindingDefinition.keys``.

Das widerspricht bewusst dem Contract (bw-gui ``docs/KEYBINDING_CONTRACT.md``,
"Rule for apps": keine Tk-Strings, kein ``bind_all`` in App-Code). Die eigentliche
Loesung ist die Migration auf ``ApplicationShortcutBinder`` + ``KeySpec`` +
``EventResult``; mit ihr wird diese Datei samt allen Aufrufern ersatzlos entfernt.
Neue Shortcuts NICHT hierueber anlegen.
"""

from __future__ import annotations

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.contracts.key_spec import Key, KeySpec, Mod  # noqa: E402

_TK_MODIFIERS = {"control": Mod.CTRL, "alt": Mod.ALT, "shift": Mod.SHIFT}

_TK_KEYSYMS = {
    "return": Key.ENTER,
    "kp_enter": Key.ENTER,
    "escape": Key.ESCAPE,
    "tab": Key.TAB,
    "space": Key.SPACE,
    "backspace": Key.BACKSPACE,
    "delete": Key.DELETE,
    "insert": Key.INSERT,
    "home": Key.HOME,
    "end": Key.END,
    "prior": Key.PAGE_UP,
    "next": Key.PAGE_DOWN,
    "up": Key.UP,
    "down": Key.DOWN,
    "left": Key.LEFT,
    "right": Key.RIGHT,
    **{f"f{n}": Key[f"F{n}"] for n in range(1, 13)},
}

# Tk-Keysym-Namen fuer druckbare Zeichen; der Ziffernblock ist in KeySpec nicht unterscheidbar.
_TK_CHAR_KEYSYMS = {
    "plus": "+",
    "kp_add": "+",
    "minus": "-",
    "kp_subtract": "-",
    "equal": "=",
}


def tk_sequence_to_keyspec(sequence: str) -> KeySpec | None:
    """Liefert die ``KeySpec`` zu einer Tk-Tastatursequenz oder ``None`` fuer Nicht-Tasten.

    Shift auf Buchstaben wird wie im Contract in den Grossbuchstaben gefaltet
    (``<Control-Shift-e>`` = ``Ctrl+Shift+E``).
    """

    parts = sequence.strip().strip("<>").split("-")
    modifiers: set[Mod] = set()
    while len(parts) > 1 and parts[0].lower() in _TK_MODIFIERS:
        modifiers.add(_TK_MODIFIERS[parts.pop(0).lower()])
    if len(parts) == 2 and parts[0] in ("Key", "KeyPress"):
        parts.pop(0)
    if len(parts) != 1 or not parts[0]:
        return None

    keysym = parts[0]
    named = _TK_KEYSYMS.get(keysym.lower())
    if named is not None:
        return KeySpec(named, modifiers)
    keysym = _TK_CHAR_KEYSYMS.get(keysym.lower(), keysym)
    if len(keysym) != 1:
        return None
    if Mod.SHIFT in modifiers:
        modifiers.discard(Mod.SHIFT)
        keysym = keysym.upper()
    return KeySpec.char(keysym, modifiers)
