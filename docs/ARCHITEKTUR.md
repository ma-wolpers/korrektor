# Architektur Korrektor

## Schichten

- Adapter: GUI und Bootstrap/Wiring
- Core: Domain, UseCases, Ports
- Infrastructure: Dateisystem-Persistenz (JSON, CSV), PDF-Scan

## Grundregeln

1. GUI enthaelt keine fachliche Entscheidungslogik.
2. UseCases orchestrieren fachliche Ablaufe.
3. Ports definieren Schnittstellen, Infrastructure liefert Implementierungen.
4. Persistenz erfolgt direkt bei relevanten UI-Ereignissen (Fokuswechsel, Navigation, Escape aus Feld).
5. Hauptansichten sind klar getrennt: Uebersicht, Klausur-Detail und Einlesen.
6. Die alte SplitView-Pane-Aufteilung ist entfernt; Ansichtswechsel laufen explizit ueber View-State.
7. KeyBindings werden zentral in `bw_libs/ui_contract/keybinding.py` definiert.
8. Pop-up-Verhalten wird zentral in `bw_libs/ui_contract/popup.py` definiert.
9. HSM-Vertragslogik fuer Intent-Katalog, Escape-Prioritaet und Transition-Validierung liegt zentral in `bw_libs/ui_contract/hsm.py`.
10. Inhaltsmutationen werden grundsaetzlich undo/redo-faehig als Session-History gefuehrt (Controller registriert Aktionen zentral).

## Persistenz

- Klausur-Metadaten: konfigurierbarer JSON-Indexordner (`*.json`, Standard: `.korrektor_index` im Repo)
- Korrekturdaten: `korrektor_scores.csv` im Klausurordner
- App-Einstellungen: `%APPDATA%/<app_name>/settings.json` (mindestens `exam_index_dir`)
- Schreibvorgaenge sind atomar (temp + replace)

## Undo/Redo

- Session-lokale History mit Rueckgaengig/Wiederholen liegt in `app/adapters/undo/history.py`.
- UI-Zugriff erfolgt ueber `Bearbeiten`-Menue sowie Shortcuts `Strg+Z` und `Strg+Y`.
- Controller-Mutatoren registrieren Undo/Redo-Aktionen zentral in `app/adapters/gui/ui_intent_controller.py`.

## Extra-Seiten-Workflow

- Im Extraseitenmodus ist derselbe Bereichseditor wie im Einlesemodus sichtbar (Aufgaben-Eingabe, Speichern, Loeschen).
- Bereichsrahmen koennen direkt auf Extraseiten gezogen, gespeichert und wieder geloescht werden.
