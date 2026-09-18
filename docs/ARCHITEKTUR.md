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
6a. Tkinter-Pack-Falle: Ein `pack_forget()` gefolgt von `pack()` OHNE `before=`/`after=` haengt das Widget ans Ende der Pack-Reihenfolge seines Masters an - liegt dort bereits ein staendig gepacktes `expand=True`-Geschwister (z. B. `self._reading_split`), landet das wieder eingeblendete Widget dahinter und bekommt keinen sichtbaren Platz mehr. Jedes in `_set_detail_submode` per Moduswechsel ein-/ausgeblendete `_reading_view`-Kind-Widget muss deshalb `before=self._reading_split` (oder ein aequivalentes Ankerwidget) setzen, nicht nur beim ersten Anzeigen, sondern bei jedem erneuten `pack()`.
7. KeyBindings werden zentral in `bw_libs/ui_contract/keybinding.py` definiert.
8. Pop-up-Verhalten wird zentral in `bw_libs/ui_contract/popup.py` definiert.
9. HSM-Vertragslogik fuer Intent-Katalog, Escape-Prioritaet und Transition-Validierung liegt zentral in `bw_libs/ui_contract/hsm.py`.
10. Inhaltsmutationen werden grundsaetzlich undo/redo-faehig als Session-History gefuehrt (Controller registriert Aktionen zentral).

## Persistenz

- Klausur-Metadaten: konfigurierbarer JSON-Indexordner (`*.json`, Standard: `.korrektor_index` im Repo)
- Korrekturdaten: `korrektor_scores.csv` im Klausurordner
- App-Einstellungen: `%APPDATA%/<app_name>/settings.json` (mindestens `exam_index_dir`)
- Schreibvorgaenge sind atomar (temp + replace)
- Zukunfts-Schema (ohne Legacy-Fallback):
	- `regions` enthalten nur Standardbereich-Templates (seiten-/koordinatenbasiert, nicht studentgebunden).
	- Extraseiten-Zuordnungen liegen separat in `extra_page_assignments` (student-/seitenbezogen).
	- JSON ohne `extra_page_assignments` wird als nicht unterstuetztes Altschema abgewiesen.

## Regionen-Identitaet

- `RegionAssignment.region_id` ist die alleinige technische Identitaet einer Region (stabile UUID, bei Erzeugung vergeben, nie neu berechnet).
- `assigned_area_codes[0]` ist ein sichtbares, fuer die Lebensdauer der Region stabiles Label (z. B. "A") - keine technische Primaeridentitaet. Nach dem Loeschen einer Region darf ihr Label spaeter an eine neu angelegte Region vergeben werden; das Loeschen einer Region veraendert nie Identitaet oder Label einer anderen Region.
- Externe Referenzen (`PersonAreaCompletion.region_id`, `PdfAnnotation.region_id`) zeigen auf `region_id`, nicht auf das Label. `TaskDefinition.code` (`task_code`) ist davon unabhaengig und muss klausurweit eindeutig sein (Score-Spalten in `korrektor_scores.csv` sind allein ueber `task_code` geschluesselt).
- Beim Laden wird die Struktur validiert (`app/core/domain/validation.py: validate_regions`): doppelte/leere `region_id`, doppelte Bereichs-Labels oder doppelte `task_code`s fuehren zu einem `ExamStructureError` statt zu stillschweigendem Datenverlust. Legacy-JSON mit altem `area_code`-Feld wird vorher, auf dem rohen Dict, migriert (`app/infrastructure/repositories/legacy_migration.py`) - nur wenn die Zuordnung eindeutig auflösbar ist, sonst bleibt sie unmigriert und die Validierung schlaegt kontrolliert fehl.
- Eine fehlerhafte Klausur-Datei wird beim Laden der Uebersicht uebersprungen (nicht angezeigt) statt die gesamte Uebersicht abzubrechen; das Oeffnen einer einzelnen fehlerhaften Klausur zeigt einen Fehlerdialog.

## Undo/Redo

- Session-lokale History mit Rueckgaengig/Wiederholen liegt in `app/adapters/undo/history.py`.
- UI-Zugriff erfolgt ueber `Bearbeiten`-Menue sowie Shortcuts `Strg+Z` und `Strg+Y`.
- Controller-Mutatoren registrieren Undo/Redo-Aktionen zentral in `app/adapters/gui/ui_intent_controller.py`.

## Extra-Seiten-Workflow

- Bereichsrahmen koennen direkt auf Extraseiten gezogen, gespeichert und wieder geloescht werden.
- Extraseiten erhalten keine eigene Aufgabenpflege; sie werden nur vorhandenen Standard-Bereichen zugeordnet.
- Standardbereiche dienen als wiederverwendbare Koordinatenvorlagen fuer alle Schueler:innen; Extraseiten referenzieren diese Bereiche nur per Zuordnung.

## Aktueller Umbau (Modi)

- Die Korrektur laeuft in einer eigenen Ansicht (separat von Klausur-Details und Einlesen) und nicht mehr als eingebetteter Formularblock in der Detailansicht.
- Die Detailansicht bleibt Hub fuer den Moduswechsel (Einlesen, Extraseiten, Namen, Korrektur).
- Im Extraseitenmodus werden keine neuen Aufgaben definiert; es sind nur Zuordnungen zu bereits vorhandenen Standard-Bereichen erlaubt.
- Namenmodus (Namen aendern/PDFs umbenennen) hat zwei Teilschritte in derselben Ansicht: Bereich-Definition (teilt sich Canvas, Seiten-/Superseiten-Navigation mit dem Einlesemodus - ein Drag committet dort aber sofort `exam.name_region`, kein Draft/Aufgaben-Schritt) und Namenserfassung (eigenes, zugeschnittenes Einzelseiten-Rendering, Pfeiltasten wechseln Schueler:in, Name wird nur in-memory gesammelt bis "Alle umbenennen").

## Gemeinsame technische Mechanismen (nicht pro Modus duplizieren)

- **Superseiten-Rendering** (`MainWindow._render_superposed_page`): ein Renderer fuer "mehrere PDFs, eine Seite, dunkel-gewinnt-Komposit", nimmt die Schueler:innen-Menge als expliziten Parameter. Einlesemodus und Namenmodus (Bereich-Definition) uebergeben `exam.students`; ein spaeterer gefilterter Anwendungsfall (Supersymbol) uebergibt eine Teilmenge. Der Renderer kennt nur "wer + welche Seite", nie *warum* diese Menge gewaehlt wurde.
- **Umbenennen als rollback-faehige Gesamtoperation** (`UiIntentController.rename_students_immediate`): Preflight (1:1-Rename-Set-Check gegen den Ordnerinhalt, Zielnamen-Planung mit interner Kollisionsaufloesung, externe Konfliktpruefung) -> zweiphasiges Staged-Rename ueber Temp-Namen (loest A<->B-Tauschfaelle, rollt bei jedem Fehler zurueck) -> In-Memory-Update -> `save_exam` -> eine `HistoryAction` mit den konkreten alt/neu-Dateinamen-Paaren (Undo/Redo spielt sie ab, berechnet sie nie neu). Rollback deckt nur waehrend des Aufrufs erkannte Laufzeitfehler ab, keine Crash-Atomicity (ein harter Prozess-/OS-Absturz mitten im Ablauf ist nicht garantiert wiederherstellbar). `MainWindow.invalidate_doc_cache` schliesst betroffene PDF-Handles vor jedem Rename.
