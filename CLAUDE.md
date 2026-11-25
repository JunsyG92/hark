# CLAUDE.md — conventions du projet Hark

Assistant de réunion **local-first** : Electron (`app/`) + moteur Python sidecar (`engine/`).
Lire d'abord `docs/architecture.md` et `docs/decisions.md`.

## Règles non négociables (à vérifier dans chaque changement)
- Aucune donnée ne quitte la machine par défaut. Aucun appel réseau hors `127.0.0.1` dans le moteur
  (sauf fournisseur LLM cloud explicitement activé). Pas de télémétrie.
- Jamais d'enregistrement sans clic explicite de l'utilisateur. La détection ne fait que **mesurer un niveau** (aucun
  échantillon audio n'est stocké ni transmis) et poser une question ; seule la réponse `record` du toast peut déclencher
  `DetectorService.on_accept` → `Recorder.start`. L'API de démarrage manuel est réservée au scope `ui`.
- Les tâches venant de l'IA, des plugins ou du MCP arrivent **toujours** dans `to_validate`
  (`TaskProposal` n'a pas de champ `column`). Seul le scope `ui` modifie, déplace ou supprime.
- L'API n'écoute que sur `127.0.0.1` ; le token ne quitte jamais le process main d'Electron.
- Validation stricte des entrées (`extra="forbid"`), aucune exécution de code fourni par un plugin.
- **Jamais de vraies données de réunion dans les tests** : audio et transcriptions synthétiques uniquement.

## Commandes
```bash
pnpm install && (cd engine && uv sync)     # installation
pnpm dev                                   # app + moteur (le moteur est lancé par Electron)
scripts/check.sh                           # tout le lint + tous les tests
cd engine && uv run pytest -q              # tests moteur
cd engine && uv run hark-engine --port 0   # moteur seul (handshake JSON sur stdout)
cd engine && uv run hark-contracts         # régénère /contracts depuis les modèles Pydantic
pnpm contracts:types                       # régénère app/src/renderer/src/lib/contracts.gen.ts
pnpm --filter @hark/app build && xvfb-run -a pnpm --filter @hark/app e2e   # smoke test Electron
```

## Organisation
- `engine/src/hark_engine/`
  - `models.py` — modèle de données partagé (**source de vérité** des contrats)
  - `api/` — FastAPI ; `deps.py` = auth et scopes (`ReadScope`, `ProposeScope`, `UiScope`)
  - `store/` — SQLite ; migrations `store/migrations/NNNN_nom.sql` (numérotation contiguë, jamais modifier une migration publiée)
  - `audio/` — niveaux audio (`levels.py` RMS dBFS, `source.py` loopback via `soundcard`, import tardif)
  - `detect/` — `machine.py` (pur, horloge injectable), `probes.py` (micro utilisé par OS), `service.py` (threads → événement `meeting.detected`)
  - `record/` — `recorder.py` (deux pistes WAV, threads, reprise après crash), `silence.py` (pur, fin de réunion)
  - `events.py` — bus d'événements interne
  - `auth.py` — token maître (keyring, repli fichier 0600)
  - `main.py` — point d'entrée sidecar (handshake stdout, logs sur stderr)
- `app/src/main/` — process main Electron (tray, raccourci, fenêtre, cycle de vie du moteur, proxy API)
- `app/src/preload/` — `index.ts` : pont `window.hark` (kanban) ; `toast.ts` : surface minimale du toast (recevoir un prompt, envoyer une réponse)
- `app/src/renderer/` — React ; logique pure dans `lib/` (testée), composants dans `components/`
- `contracts/` — JSON Schema + OpenAPI **générés** (ne pas éditer à la main)
- `docs/increments/` — une note par étape livrée (ce qui a été fait + comment tester à la main)

## Pièges connus
- **uvicorn re-lève le signal d'arrêt juste après son shutdown** : tout code placé *après* `server.run()` peut ne jamais
  s'exécuter. La finalisation (arrêt de l'enregistrement) vit dans le `lifespan` de `create_app`. Fermer stdin ⇒
  `server.should_exit = True` (arrêt propre), jamais `os.kill(SIGTERM)`.
- Un enregistrement doit rester récupérable : WAV + flush par bloc ; `recover_interrupted()` recompte les vraies images.
- Dans les tests/e2e Electron, `getAllWindows()[0]` n'est pas le kanban : sélectionner par URL (`index.html`).
- `HARK_FAKE_AUDIO=1` : sources audio synthétiques (ton 440 Hz système, micro quasi muet) pour tester sans périphérique.

## Conventions
- Python : ruff (lint + format), mypy strict, pytest. Pydantic v2. `from __future__ import annotations`
  partout **sauf** si FastAPI doit résoudre des alias `Annotated` locaux (les mettre au niveau module).
- TypeScript : strict, eslint, vitest. Logique pure séparée des composants pour être testable.
- Modifier un modèle ⇒ `uv run hark-contracts` puis `pnpm contracts:types` (des tests vérifient la synchro).
- Toute nouvelle route : un scope explicite + un test 401/403 + un test de validation 422.
- UI et docs utilisateur en français ; code, identifiants et commentaires en anglais.
- Chaque étape livrée met à jour `README.md` (tableau d'avancement), ce fichier si besoin, et ajoute `docs/increments/NN-*.md`.
