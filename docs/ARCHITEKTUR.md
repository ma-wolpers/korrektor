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
- `HistoryAction.context` (`"content"` | `"lifecycle"`, Default `"content"`) steuert ausschliesslich, *wie* die UI nach einem Undo/Redo aktualisiert wird - keine allgemeine Klassifikation aller Aktionsarten. `"content"` (jede Mutation an einer bereits offenen Klausur: Annotationen, Punkte, Regionen, Umbenennen, ...) laedt die Klausur ueber `MainWindow.refresh_exam_content_in_place()` neu, ohne Moduszustand/View/Cursor zurueckzusetzen. `"lifecycle"` (Klausur anlegen/loeschen, JSON-Ablageordner wechseln - aktuell nur die drei Call-Sites in `ui_intent_controller_overview.py`) behaelt den vollen Navigations-Reset zurueck zur Uebersicht/Detailansicht (`sync_current_exam_from_repository()`/`open_exam_detail()`), da sich dort die Klausur-Identitaet selbst aendert. "Kontext erhalten" ist dabei eine Zielvorgabe fuer den Regelfall, keine Garantie: macht die Aktion selbst eine UI-Referenz obsolet (z. B. Undo von "Markierung gesetzt" entfernt die gerade ausgewaehlte Annotation), darf/soll diese Referenz sauber verschwinden statt kuenstlich erhalten zu bleiben.
- Sofortige JSON-Persistenz einer Inhaltsaenderung und der physische PDF-Export ("Alle PDFs ueberschreiben") sind bewusst getrennte Schritte: `Strg+Z` auf eine Annotation macht ausschliesslich die Exam-JSON-Aenderung rueckgaengig, eine zuvor bereits exportierte physische PDF-Datei wird dadurch nicht erneut angefasst - ein erneutes "Alle PDFs ueberschreiben" ist der einzige Weg, den PDF-Stand an einen per Undo veraenderten Exam-Zustand anzugleichen.

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

- **Superseiten-Rendering, in zwei Schichten getrennt:** `MainWindow._build_superposed_pixmap` ist die reine Berechnung ("mehrere PDFs, eine Seite -> ein dunkel-gewinnt-Graustufen-Pixmap", keine Tkinter-Seiteneffekte), nimmt die Schueler:innen-Menge als expliziten Parameter und kennt nie *warum* diese Menge gewaehlt wurde. Die Anzeige ist bewusst NICHT dieselbe Funktion, weil Einlesemodus/Namenmodus (`_render_superposed_page`, volle Seite, `_reading_canvas`, `_x_factor`/`_y_factor`) und Korrekturmodus/Supersymbol (`_render_supersymbol_filtered_page`, ebenfalls volle Seite aber auf `_correction_canvas`, ueber `_correction_clip_box`/`_correction_scale` mit Clip = ganze Seite) bereits unterschiedliche, etablierte Koordinatensysteme benutzen - beide Anzeige-Funktionen rufen dieselbe `_build_superposed_pixmap` auf, bauen das Bild aber mit ihrer eigenen Skalierungs-Konvention ins jeweils richtige Canvas.
- **Umbenennen als rollback-faehige Gesamtoperation** (`UiIntentController.rename_students_immediate`): Preflight (1:1-Rename-Set-Check gegen den Ordnerinhalt, Zielnamen-Planung mit interner Kollisionsaufloesung, externe Konfliktpruefung) -> zweiphasiges Staged-Rename ueber Temp-Namen (loest A<->B-Tauschfaelle, rollt bei jedem Fehler zurueck) -> In-Memory-Update -> `save_exam` -> eine `HistoryAction` mit den konkreten alt/neu-Dateinamen-Paaren (Undo/Redo spielt sie ab, berechnet sie nie neu). Rollback deckt nur waehrend des Aufrufs erkannte Laufzeitfehler ab, keine Crash-Atomicity (ein harter Prozess-/OS-Absturz mitten im Ablauf ist nicht garantiert wiederherstellbar). `MainWindow.invalidate_doc_cache` schliesst betroffene PDF-Handles vor jedem Rename.
- **Bulk-Annotation-Klonen** (`app/core/domain/annotation_sync.py: build_annotation_clones`): reine Funktion, die eine Basis-Annotation fuer eine gegebene Schueler:innen-Menge klont und ihnen eine gemeinsame `sync_group_id` gibt. Sowohl "Durchdruecken" (`MainWindow._enable_selected_annotation_sync`, Ziel: alle anderen Korrektur-Schueler:innen) als auch das Supersymbol (`UiIntentController.apply_super_symbol_immediate`, Ziel: die score-gefilterte Teilmenge) rufen dieselbe Funktion mit unterschiedlicher `students`-Liste auf.
- **Supersymbol** (`app/core/domain/score_filter.py` + `UiIntentController.apply_super_symbol_immediate`): Filterlogik (`compute_student_value`/`matches_condition`/`filter_matching_student_ids`) ist reine, UI-freie Fachlogik. 0 Treffer ist ein Fehlerfall (keine darstellbare Superseite), kein leerer Zustand. Die Aktion ist ein einmaliger Bulk-Apply: alle N erzeugten `PdfAnnotation`s teilen sich eine `sync_group_id` und werden als eine `HistoryAction` (Snapshot-Muster) undo-/redo-faehig - spaetere Punkte-Aenderungen bewegen oder entfernen bereits gesetzte Supersymbole nie automatisch. Der gefilterte Superseiten-Klick nutzt `_correction_clip_box`/`_correction_scale` mit Clip = ganze Referenzseite (statt `template.box`), damit `_canvas_to_pdf_coords` ohne neue Umrechnung fuer jede/n Treffer dieselbe absolute PDF-Position liefert.

## Datei-Organisation (~300-Zeilen-Konvention)

`main_window.py` und `ui_intent_controller.py` waren als einzelne Dateien weit ueber der projektweiten ~300-Zeilen-Code-Konvention (5844 bzw. 1047 Rohzeilen). Beide sind jetzt reine Fassaden: die tatsaechliche Logik liegt in `main_window_*.py`-Mixin-Dateien (Klassen `MainWindow<Domain>Mixin`, zusammengesetzt per Mehrfachvererbung mit `MainWindowBase` zuletzt in der MRO) bzw. `ui_intent_controller_*.py`-Mixin-Dateien (analog `UiIntentController<Domain>Mixin`/`UiIntentControllerBase`) - Konvention identisch zum Schwesterrepo `blattwerk` (`BlattwerkApp(BwBaseWindow)` -> `blatt_ui_*.py`). Mixins definieren bewusst kein eigenes `__init__`; die Fassaden re-exportieren alles, was externer Code (insbesondere Tests) importiert oder patcht.

**Bewusste Ausnahme:** `main_window_region_editor.py` liegt mit ~391 Zeilen Code ueber der 300-Zeilen-Konvention - bewusst nicht weiter zerlegt. Der Ueberhang stammt aus einer einzigen, echten Kopplung: Reading-Modus und Extraseiten-Modus teilen sich einen Treeview (`_regions_tree`/`_region_tree_rows`), eine Selektion (`_selected_region_id`/`_selected_region_kind`) und ein Draft-Dict (`_draft_regions`), sodass Treeview-Aufbau, Selektions-Handling, Speichern/Loeschen, die drei geteilten Render-Helfer (`_build_superposed_pixmap`, `_render_pdf_page`, `_wheel_direction`) UND die Widget-Konstruktion fuer genau diesen Mechanismus (`_build_reading_view_region_editor`, `_build_reading_view_mode_row`) zusammen bleiben muessen - ein modusbasierter Split wuerde diese Kopplung nur ueber mehrere Dateien verteilen statt sie zu kapseln (siehe die reinen Formatierungs-/Lookup-Helfer, die bereits als `main_window_region_specs.py` ausgelagert sind, weil sie diese Kopplung nicht teilen).
- **Einzel- auf Mehrfach-Personen generalisieren, statt zu duplizieren** (`UiIntentController.set_persons_area_finished_immediate`, vormals `set_person_area_finished_immediate`): derselbe `_immediate`-Stil wie ueberall sonst (Validierung -> Mutation -> `save_exam`/`load_exam` -> eine `HistoryAction` via `_record_exam_payload_action`), nur dass `student_ids` jetzt `Sequence[str]` statt `str` ist. Bei genau einer ID ist das Verhalten byte-identisch zur fruehreren Einzelfassung (gleiche Fehlermeldungen/Status-/History-Texte); Validierung ist alles-oder-nichts (eine unbekannte ID verwirft die komplette Aktion, kein Best-Effort-Teilupdate). Die begleitende, rein lesende `count_persons_area_finished` dedupliziert `student_ids` bewusst NICHT selbst (die eine kanonische Quelle ist `MainWindow._correction_region_student_ids()`) - ein Zaehl-Duplikat verfaelscht nur eine Anzeige, waehrend die schreibende Methode zur Sicherheit selbst dedupliziert, weil ein Duplikat dort eine `HistoryAction` mit falscher Personenzahl erzeugen wuerde. `MainWindow._are_all_tasks_scored` folgt demselben Muster auf der Lese-Seite: eine `@staticmethod` ohne eigenes CSV-I/O, die auf bereits von `load_scores_for_exam` geladenen Daten sowohl die Einzel- als auch die Bereichs-Pruefung bedient, statt (wie zuvor `_all_tasks_scored_for_current_area`) pro Aufgabe/Person `load_saved_points` und damit die komplette CSV neu zu parsen.
