# Korrektor

Korrektor ist eine Desktop-Anwendung zur Verwaltung und Korrektur von Klausur-PDFs.

## Status

Startimplementation (M1/M2-Basis) ist vorhanden:
- Klausuruebersicht
- Neue Klausur aus PDF-Ordner anlegen
- Standardseitenzahl ueber kuerzeste Klausur bestimmen
- Persistente JSON-Indexverwaltung
- Sofortspeicherung von Punkteingaben in CSV
- Detailansicht mit Warnhinweisen fuer offene Punkte

## Setup

1. Virtuelle Umgebung erstellen:
   - `py -3 -m venv .venv`
2. Aktivieren und Abhaengigkeiten installieren:
   - `.venv\\Scripts\\activate`
   - `pip install -r requirements.txt`
   - `pip install -r requirements-dev.txt`

## Start

- `start-korrektor.bat`
- oder `python korrektor.py`

## Architektur

Schichtenmodell:
- Adapters (GUI + Wiring)
- Core (Domain, UseCases, Ports)
- Infrastructure (JSON/CSV/PDF Repositories)

Die GUI bleibt Orchestrator-nahe; fachliche Logik liegt in UseCases und Domain.
