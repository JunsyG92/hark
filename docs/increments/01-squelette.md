# Étape 1 — Squelette, tray, raccourci, kanban persistant

## Fait
- Moteur Python (`engine/`) : FastAPI sur `127.0.0.1` uniquement, token maître dans le
  gestionnaire d'identifiants de l'OS, migrations SQLite versionnées, CRUD des tâches, déplacement
  ordonné, `POST /v1/tasks/propose` (toujours « À valider »), bus d'événements interne
  (`task.updated`, `task.proposed`), garde anti DNS-rebinding / Origin.
- Contrats : `contracts/{Task,TaskProposal,EvidenceRef,Event}.schema.json` + `openapi.json`,
  générés depuis Pydantic ; types TS générés pour le front.
- App Electron (`app/`) : icône tray (menu : ouvrir, lancer au démarrage, quitter), raccourci global
  `Ctrl+Alt+K` configurable (portail XDG activé pour Wayland), fenêtre kanban pré-chargée et cachée,
  4 colonnes, glisser-déposer (souris + clavier), création rapide, éditeur (titre, description,
  assigné, échéance, priorité, source, extrait), bouton « Valider → À faire », réglages.
- Tests : 16 pytest, 15 vitest, smoke e2e Electron (Playwright) qui mesure l'affichage (< 300 ms,
  mesuré ~1–2 ms sous Xvfb) et vérifie la persistance après redémarrage.

## Tester à la main
```bash
pnpm install
cd engine && uv sync && cd ..
pnpm dev
```
1. L'icône Hark apparaît dans la zone de notification ; la fenêtre kanban s'ouvre (en dev).
2. `Échap` la masque, `Ctrl+Alt+K` la réaffiche instantanément.
3. Ajoute des tâches (champ en bas de colonne ou touche `N`), déplace-les, clique pour les éditer.
4. Quitte (menu tray → Quitter), relance : les tâches sont toujours là.
5. Simule une intégration :
   ```bash
   # le token est affiché nulle part : récupère-le via le gestionnaire d'identifiants
   # (service "hark", compte "api-token"), ex. sous Linux :
   TOKEN=$(secret-tool lookup service hark username api-token)
   PORT=$(python3 -c "import json,platformdirs as p;print(json.load(open(p.user_data_dir('Hark',appauthor=False)+'/runtime.json'))['port'])")
   curl -s -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
     http://127.0.0.1:$PORT/v1/tasks/propose -d '{"title":"Relancer Paul sur le budget Q1"}'
   ```
   La tâche apparaît dans « À valider » à la prochaine ouverture du kanban.

## Limites connues
- Le rafraîchissement du kanban se fait à l'ouverture de la fenêtre (le flux temps réel SSE arrive à l'étape 6).
- Pas encore de binaire packagé du moteur (PyInstaller prévu avant la première release) : en dev, `uv` est requis.
