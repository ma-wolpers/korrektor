# Changelog

## Unreleased
- Foundation for unified keyboard and popup governance: central modules `app/adapters/gui/keybinding_registry.py` and `app/adapters/gui/popup_policy.py` are now part of the app structure.
- Guardrail foundation added: AGENTS, Copilot instructions, PR template, and CI/local check script for repository governance.
- Neues Projekt `Korrektor` fuer Klausurverwaltung gestartet.
- Erste lauffaehige GUI mit Klausuruebersicht und Detailansicht.
- Sofortspeicherung fuer Punkteingaben in CSV hinzugefuegt.
- Einlesemodus mit PDF-Vorschau, Rechteck-Markierung und direkter Regionsspeicherung in JSON hinzugefuegt.
- Warnung beim Abschliessen des Einlesens bei noch unmarkierten Standardseiten implementiert.
- Separater Extraseiten-Modus mit sequenzieller Anzeige ueber alle Extraseiten implementiert.
- Direkte Bereichszuordnung fuer Extraseiten (A/B/C...) mit sofortiger JSON-Speicherung hinzugefuegt.
- Bereichsbasierter Korrekturmodus mit schneller Navigation ueber passende Schueler:innen hinzugefuegt.
- Escape-Tastaturverhalten als Navigation pro Ebene umgesetzt (Modus -> Detail -> Gesamtuebersicht).
- Extraseitenansicht im Korrekturmodus bei Fallwechsel automatisch aktualisiert und bei Moduswechsel sauber geschlossen.
- Beim Wechsel des Falls landet der Fokus automatisch im ersten Eingabefeld.
- PDF-Vorschau in Einlese- und Extraseitenansicht verlässlich sichtbar gemacht; bei Renderfehlern wird eine klare Fehlermeldung angezeigt.
- Nach dem Anlegen einer neuen Klausur startet der Einlesemodus automatisch.
- Schnellkorrektur-Block wird nur noch im aktiven Korrekturmodus angezeigt.
- Klausur kann nun auch per Enter oder Doppelklick aus der Liste geoeffnet werden.
- `.gitignore` fuer lokale Entwicklungsartefakte (venvs, caches, lokale Indexdaten, Konfigurationsreste) hinzugefuegt.
- Beginn des Modus-Umbaus: Beim Oeffnen einer Klausur wechselt die Ansicht in einen separaten Detailmodus; Rueckkehr per "Zur Uebersicht".
- Einlesemodus zeigt nun ein scrollbares PDF-Viewport mit Inline-Bereichsliste und Inline-Bereichseditor statt Aufgaben-Popup.
- Bereiche werden automatisch benannt (A, B, ..., Z, AA, ...); nach Loeschen werden Bereichsnamen kompakt neu vergeben.
- Detailmodus bietet jetzt explizite Submodi fuer Einlesen, Korrektur und Extraseiten mit passender UI pro Modus.
- Bereiche sind direkt in der PDF-Vorschau anklickbar und koennen inline bearbeitet oder geloescht werden.
- Beim Navigieren (Seite/Person) werden offene Bereichsaenderungen automatisch gespeichert.
