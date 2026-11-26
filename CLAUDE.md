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
- **Aucun appel réseau hors loopback** est appliqué par `net/guard.py`. Tout nouveau code qui voudrait le réseau doit
  passer par une action explicite de l'utilisateur et `allow_network()` ; ne jamais désactiver la garde.
- **Électron aussi doit rester local** : `app/src/main/network.ts` (interrupteurs Chromium, noms non locaux irrésolvables,
  requêtes non locales annulées). Après toute mise à jour d'Électron ou ajout de code réseau côté app : `scripts/audit-network.sh`
  doit afficher OK. Ne jamais appeler une URL non locale depuis `app/`.
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
pnpm --filter @hark/app build && xvfb-run -a -s "-screen 0 1600x1000x24" pnpm --filter @hark/app e2e   # smoke test Electron
```

## Organisation
- `engine/src/hark_engine/`
  - `models.py` — modèle de données partagé (**source de vérité** des contrats)
  - `api/` — FastAPI ; `deps.py` = auth et scopes (`ReadScope`, `ProposeScope`, `UiScope`)
  - `store/` — SQLite ; migrations `store/migrations/NNNN_nom.sql` (numérotation contiguë, jamais modifier une migration publiée)
  - `audio/` — niveaux audio (`levels.py` RMS dBFS, `source.py` loopback via `soundcard`, import tardif)
  - `detect/` — `machine.py` (pur, horloge injectable), `probes.py` (micro utilisé par OS), `service.py` (threads → événement `meeting.detected`)
  - `record/` — `recorder.py` (deux pistes WAV, threads, reprise après crash), `silence.py` (pur, fin de réunion)
  - `stt/` — `profiles.py` (modèles/recommandation), `models.py` (téléchargement explicite), `transcriber.py` (faster-whisper / factice), `service.py` (file d'attente, rétention)
  - `llm/` — `provider.py` (interface + fournisseur factice), `ollama.py` (local), `cloud.py` (désactivé par défaut), `profiles.py`, `factory.py`
  - `analysis/` — `chunking.py`, `prompts.py` (**changer un prompt ⇒ incrémenter `PROMPT_VERSION`**), `pipeline.py` (budget, parsing), `mine.py` (« me concernant »), `service.py` (file, cache par hash, création des tâches)
  - `profile.py` — `profile.yaml` (YAML sûr, validé) ; `net/guard.py` — garde réseau (loopback seulement) ; `export.py` — export Markdown (pur)
  - `store/people.py` — annuaire d'équipe (`match()` : rattachement non ambigu d'un nom entendu)
  - `progress/` — gamification : `rules.py` (pur : points, niveaux, séries, badges), `service.py` (journal `activity`, résumés jour/mois/année) ; alimenté par `POST /v1/tasks/{id}/move`
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
- `HARK_FAKE_STT=1` : transcription factice (deux segments fr) et modèles « installés », pour tester sans télécharger.
  Le vrai faster-whisper n'a un test d'intégration qu'en opt-in : `HARK_TEST_REAL_STT=1 uv run pytest tests/test_real_stt.py -s`.
- Hugging Face ne doit jamais passer en ligne seul : `HF_HUB_OFFLINE=1` est posé au démarrage ; seul le téléchargement
  explicite le bascule temporairement.
- `HARK_FAKE_LLM=1` : LLM factice déterministe (2 tâches, résumé) pour les tests/e2e. Le vrai Ollama n'est testé que contre
  un faux serveur HTTP local (contrat de l'API) : il n'a pas été exécuté en CI.
- Les tâches créées par l'analyse passent par `TaskRepository.propose` : **toujours** `to_validate`.
- Le kanban est un **panneau latéral** étroit (`panelGeometry.ts`) : en e2e, lancer Xvfb avec un grand écran
  (`xvfb-run -a -s "-screen 0 1600x1000x24"`), sinon les sections du bas sont hors écran.
- Le panneau se masque sur perte de focus (`blur.ts`) : toute boîte de dialogue native ouverte depuis le panneau doit passer par
  `KanbanWindow.withDialog()`, et jamais `window.confirm()` dans le renderer (utiliser `window.hark.confirm`).
  Test réel au clic : `xvfb-run -a -s "-screen 0 1600x1000x24" scripts/e2e-outside-click.sh` (openbox, xdotool, xterm).
- `HARK_FAKE_AUDIO=1` : sources audio synthétiques (ton 440 Hz système, micro quasi muet) pour tester sans périphérique.

## Conventions
- Python : ruff (lint + format), mypy strict, pytest. Pydantic v2. `from __future__ import annotations`
  partout **sauf** si FastAPI doit résoudre des alias `Annotated` locaux (les mettre au niveau module).
- TypeScript : strict, eslint, vitest. Logique pure séparée des composants pour être testable.
- Modifier un modèle ⇒ `uv run hark-contracts` puis `pnpm contracts:types` (des tests vérifient la synchro).
- Toute nouvelle route : un scope explicite + un test 401/403 + un test de validation 422.
- UI et docs utilisateur en français ; code, identifiants et commentaires en anglais.
- Chaque étape livrée met à jour `README.md` (tableau d'avancement), ce fichier si besoin, et ajoute `docs/increments/NN-*.md`.
