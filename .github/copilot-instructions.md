# Copilot Instructions (korrektor)

Arbeite in einfacher, klarer Struktur.

Pflichtregeln:

1. Architektur-Referenz
- `docs/ARCHITEKTUR.md` beschreibt nur den aktuellen Zustand.
- Keine Abschluss-/Historienlisten im Architekturdokument.

2. Development-Log
- Bei Feature- und Architektur-Aenderungen immer `docs/DEVELOPMENT_LOG.md` im selben Zyklus aktualisieren.
- Bugfix-Only-Aenderungen sind davon ausgenommen.

3. Public Changelog
- Nutzerrelevante Aenderungen in `CHANGELOG.md` eintragen.

4. Zentrale UI-Module
- KeyBindings zentral in `bw_libs/ui_contract/keybinding.py` verwalten.
- Pop-up-Regeln zentral in `bw_libs/ui_contract/popup.py` verwalten.
- Neue Shortcut-/Popup-Funktionen zuerst zentral registrieren, dann in Views anbinden.

5. Commit-/Push-Workflow
- Feature-Aenderungen als eigene Commits strukturieren.
- Push bleibt manuell; kein automatisches Pushen.

6. Guardrails sind bindend
- `tools/ci/check_ai_guardrails.py` muss lokal und in CI bestehen.
