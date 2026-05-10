# Agent Guardrails (korrektor)

Dieses Repository hat verbindliche Leitplanken fuer KI-Programmierer.

Ziel in einfachen Worten:
- Architektur stabil und nachvollziehbar halten.
- UI-Steuerung fuer Tastatur und Pop-ups zentral verwalten.
- Feature-Arbeit klar committen, Push bewusst manuell halten.

Verbindliche Regeln:

1. Architektur-Dokumentrolle
- `docs/ARCHITEKTUR.md` beschreibt den aktuellen Ist-Zustand.
- Historie/Abschluesse gehoeren nicht in diese Datei.

2. Development-Log-Pflicht
- Bei Feature- und Architektur-Aenderungen muss `docs/DEVELOPMENT_LOG.md` im selben Zyklus aktualisiert werden.
- Reine Bugfix-Only-Changes koennen ohne Development-Log-Eintrag erfolgen.

3. Public-Kommunikation
- Nutzerrelevante Aenderungen werden in `CHANGELOG.md` gepflegt.
- PRs verwenden die Checkliste in `.github/pull_request_template.md`.

4. Zentrale UI-Steuerung
- KeyBindings werden zentral in `bw_libs/ui_contract/keybinding.py` verwaltet.
- Pop-up-Verhalten wird zentral in `bw_libs/ui_contract/popup.py` verwaltet.
- Neue Shortcuts und neue Pop-ups werden zuerst in den Zentralmodulen definiert.

5. Strict bw-gui-only-Policy
- Keine lokale tkinter/ttk-Widgetimplementierung in Repos.
- Neue wiederverwendbare GUI-Bausteine zuerst in bw-gui implementieren und erst danach in Repos anbinden.

6. Feature-Commit und Push-Disziplin
- Feature-Aenderungen werden in eigenstaendigen Commits gebuendelt.
- Push erfolgt manuell durch den Nutzer; kein Auto-Push.

7. Automatische Gates
- Lokaler Check und CI pruefen die Guardrails ueber `tools/ci/check_ai_guardrails.py`.
