# Décisions (ADR courtes)

| # | Décision | Pourquoi |
|---|---|---|
| 1 | **Electron** (pas Tauri) | Même Chromium sur Win/Linux/Mac ; Tauri = WebKitGTK sous Linux (tray/rendu inégaux). Le < 300 ms est obtenu en gardant la fenêtre kanban pré-chargée et cachée. |
| 2 | Moteur = **sidecar Python** (FastAPI, uv) | Écosystème audio/STT (faster-whisper, soundcard). Lancé par Electron, handshake JSON sur stdout, s'arrête quand stdin se ferme. |
| 3 | **Le token ne quitte jamais le process main** | Le renderer passe par IPC (`hark:api`) → main ajoute le Bearer. Pas de CORS, pas de token dans le DOM. |
| 4 | API **loopback only** + contrôle `Host` + refus des requêtes avec `Origin` | Protège contre le DNS rebinding et les pages web qui tenteraient d'appeler l'API locale. |
| 5 | Token maître dans le **gestionnaire d'identifiants de l'OS** (`keyring`) | Repli : fichier `0600` si aucun backend (Linux headless), avec avertissement. |
| 6 | **Pydantic = source de vérité** des contrats → `/contracts/*.schema.json` → types TS générés | Un test casse si l'un des trois dérive. |
| 7 | Les tâches venant de l'IA / plugins / MCP **ne peuvent pas choisir leur colonne** | `TaskProposal` n'a pas de champ `column` (et `extra=forbid`) : elles arrivent toujours dans « À valider ». |
| 8 | Détection de réunion : son ≥ seuil N s **+ micro utilisé par une autre app** (configurable) → notification avec **[Enregistrer] [Non]**, qui disparaît après quelques secondes (= ignorer). On n'enregistre **que** sur clic. | Réponse Q1. Le signal micro est ce qui sépare un appel d'une vidéo YouTube. |
| 9 | macOS (capture du son système) **reporté** à une version ultérieure. L'abstraction de capture le prévoit. | Réponse Q2. |
| 10 | Voix → personnes, inspiré de voicebox (`VoiceProfile` + `ProfileSample`) : `Person` + échantillons/embeddings, reconnaissance proposée, validée par l'utilisateur. Étape 4b. | Réponse Q3. |
| 11 | **Profils de modèles** (Léger / Équilibré / Précis) pour Whisper et Ollama, avec gestionnaire de téléchargement explicite. | Réponse Q4 (inspiré du gestionnaire de modèles de voicebox). |
| 12 | Fin de réunion : après X min de silence, notification « Réunion terminée ? » qui **reste affichée** jusqu'à ce qu'une voix revienne (elle se ferme, l'enregistrement continue) ou que l'utilisateur arrête. Pas d'arrêt automatique. | Réponse Q5. |
| 13 | MCP : servi par le moteur (HTTP streamable `/mcp`) **+ shim stdio** qui relaie vers lui (modèle voicebox `mcp_shim`). | Une seule implémentation, un seul point de contrôle des permissions. |
