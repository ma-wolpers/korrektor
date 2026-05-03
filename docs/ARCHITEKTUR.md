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
5. KeyBindings werden zentral in `app/adapters/gui/keybinding_registry.py` definiert.
6. Pop-up-Verhalten wird zentral in `app/adapters/gui/popup_policy.py` definiert.
7. HSM-Vertragslogik fuer Intent-Katalog, Escape-Prioritaet und Transition-Validierung liegt zentral in `app/adapters/gui/hsm_contract.py`.

## Persistenz

- Klausur-Metadaten: `.korrektor_index/*.json`
- Korrekturdaten: `korrektor_scores.csv` im Klausurordner
- Schreibvorgaenge sind atomar (temp + replace)
