# Development Log

## [Unreleased]
- Guardrail-Basis eingefuehrt: `AGENTS.md`, `.github/copilot-instructions.md`, PR-Template sowie `tools/ci/check_ai_guardrails.py` plus CI-Workflow.
- Zentrale UI-Basis fuer Tastatur- und Popup-Steuerung eingefuehrt: `app/adapters/gui/keybinding_registry.py` und `app/adapters/gui/popup_policy.py`.
- Governance erweitert: Feature-Arbeit wird als eigener Commit-Block gefuehrt, Push bleibt explizit manuell.
- Guardrails praezisiert: `CHANGELOG.md` wird nur bei nutzer- oder coentwicklerrelevanten Aenderungen erzwungen; Prozesswarnungen (Commit-/Push-Guidance) erscheinen nur lokal und nicht in CI.
- Wave-1-Start fuer den Hybrid-Resolver: `app/adapters/gui/keybinding_registry.py` enthaelt jetzt einen zentralen Runtime-Kontextvertrag (`KeybindingRuntimeContext`) und eine einheitliche `evaluate_runtime`-API fuer mode-/offline-/textfokus-/dialogbasierte Aktivierungspruefung.
- Wave-1 konkret verdrahtet: globale Shortcuts in `app/adapters/gui/main_window.py` laufen jetzt ueber den zentralen Runtime-Resolver statt direkter Bind-Dispatches.
- Tabellarische Runtime-Debug-Ansicht fuer Shortcuts im Hauptfenster ergaenzt (`Shortcut Debug`, `Strg+Shift+D`) inkl. Offline-Simulation (`Strg+Shift+O`) und Aktiv/Disabled-Gruenden pro Modus.

## 2026-04-26
- Initiales Projekt `Korrektor` erstellt.
- Grundarchitektur mit Adapter/Core/Infrastructure umgesetzt.
- Klausur-Import aus PDF-Ordner mit PyMuPDF implementiert.
- JSON-Indexpersistenz und atomare Schreibvorgaenge eingefuehrt.
- Erste Korrektur-Schnellansicht mit Sofortspeicherung in CSV integriert.
- Einlesemodus mit PDF-Seitenanzeige, Rechteck-Markierung per Maus und Bereichs-/Aufgabenzuordnung umgesetzt.
- Sofortige JSON-Speicherung jeder neu markierten Region beim Abschluss der Zuordnung eingebaut.
- Seitennavigation und Schueler:innen-Navigation im Einlesemodus ergaenzt (Buttons + Pfeiltasten links/rechts im aktiven Einlesemodus).
- Abschlusslogik fuer Einlesemodus mit Warnhinweis bei unmarkierten Standardseiten hinzugefuegt.
- Separater Extraseiten-Modus hinzugefuegt: sequenzielle Navigation ueber alle Extraseiten inkl. Anzeige Person + Index + Gesamtzahl.
- Extraseiten koennen direkt einem oder mehreren Bereichen (A,B,...) zugeordnet werden; Zuordnung wird sofort in JSON persistiert.
- Vorhandene Extraseiten-Zuordnung derselben Person/Seite wird aktualisiert statt dupliziert.
- Bereichsbasierter Korrekturmodus hinzugefuegt: Navigation nur ueber Schueler:innen mit Zuordnung im gewaehlten Bereich.
- Extraseiten-Quick-View pro aktueller Person als Popup integriert.
- Escape-Navigation auf Ebenenmodell angepasst: Feldfokus -> Modus verlassen -> Detail verlassen -> Gesamtuebersicht.
- Extraseiten-Popup-Verhalten verfeinert: beim Fallwechsel im Korrekturmodus automatische Aktualisierung/Oeffnung, bei Modusende sauberes Schliessen.
- Beim Fallwechsel springt der Fokus jetzt immer in das erste Eingabefeld der Korrekturmaske.
- UX-Hotfix: PDF-Rendering in Einlese- und Extraseitenansicht stabilisiert (robuster Fehlerpfad, sichtbare Fehlermeldung statt stiller No-Op).
- Workflow-Update: Nach `Neue Klausur` startet der Einlesemodus automatisch.
- Detailansicht angepasst: Schnellkorrektur-Bereich ist ausserhalb des Korrekturmodus ausgeblendet und wird nur im aktiven Korrekturmodus angezeigt.
- Klausurliste verbessert: erste Zeile wird nach Refresh automatisch selektiert; Oeffnen per Enter/Doppelklick unterstuetzt.
- Repo-Hygiene: `.gitignore` fuer venvs, caches, lokale Laufzeitdaten und Konfigurationsreste angelegt.
- Start Modus-Umbau: Uebersicht und Detail werden jetzt als getrennte Fensterzustände geschaltet (Liste verschwindet in Detailmodus, Back-Navigation zurueck in Uebersicht).
- Einlesemodus erweitert: Scrollbares PDF-Viewport + Inline-Bereichsliste + Inline-Bereichseditor unter der Vorschau (kein Aufgaben-Popup mehr fuer Standardbereiche).
- Bereichslogik begonnen: neue Bereiche erhalten automatische Labels (A, B, ..., Z, AA, ...); Loeschen triggert kompakte Neuvergabe.
- Bereichsbearbeitung begonnen: Bereich per Klick aus Liste laden, Aufgaben/Punkte direkt inline speichern oder loeschen (inkl. JSON-Sofortspeicherung).
- Detailmodus weiter aufgesplittet: Einlesen/Korrektur/Extraseiten als explizite Submodi mit eigener Sichtbarkeitslogik im selben Detailfenster.
- Bereichsauswahl erweitert: Bereiche koennen nun direkt im Canvas per Klick auf das Rechteck ausgewaehlt und sofort inline bearbeitet werden.
- Inline-Speicherfluss gehaertet: Bereichsaenderungen werden vor Seiten-/Personwechsel automatisch gespeichert.
- Reindex-Verhalten praezisiert: Beim Loeschen werden nur Standardbereiche neu benannt, Extraseiten-Zuordnungen bleiben erhalten.
