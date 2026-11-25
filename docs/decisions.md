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
| 8b | Précision sur la détection : le **signal d'appel est « une autre application utilise le micro »** (Linux : `pactl list source-outputs`, flux lisant une source `.monitor` exclus ; Windows : registre `CapabilityAccessManager`). Un simple processus Teams/Zoom ouvert **ne suffit pas** (il tourne toute la journée) : le nom de l'application sert seulement à étiqueter la notification. `require_mic_in_use=false` donne un mode « audio seul », moins précis. | Évite les faux positifs YouTube tout en couvrant les appels, sans IA. |
| 9 | macOS (capture du son système) **reporté** à une version ultérieure. L'abstraction de capture le prévoit. | Réponse Q2. |
| 10 | Voix → personnes, inspiré de voicebox (`VoiceProfile` + `ProfileSample`) : `Person` + échantillons/embeddings, reconnaissance proposée, validée par l'utilisateur. Étape 4b. | Réponse Q3. |
| 11 | **Profils de modèles** (Léger / Équilibré / Précis) pour Whisper et Ollama, avec gestionnaire de téléchargement explicite. | Réponse Q4 (inspiré du gestionnaire de modèles de voicebox). |
| 12 | Fin de réunion : après X min de silence, notification « Réunion terminée ? » qui **reste affichée** jusqu'à ce qu'une voix revienne (elle se ferme, l'enregistrement continue) ou que l'utilisateur arrête. Pas d'arrêt automatique. | Réponse Q5. |
| 14 | La notification de consentement est une **petite fenêtre Electron** (toujours au premier plan, affichée **sans prendre le focus**, identique sur les 3 OS), pas une notification native. Elle ne peut répondre qu'avec `record` / `decline` / `ignore` via IPC validé (l'expéditeur doit être cette fenêtre). | Les boutons d'action natifs sont peu fiables sous Linux ; ne pas voler le focus évite de perturber la réunion. |
| 15 | Flux d'événements **SSE** `/v1/events/stream` (scope `read`) dès l'étape 2 : le process main s'y abonne (toast + rafraîchissement du kanban en temps réel). Les plugins l'utiliseront à l'étape 6. | Un seul mécanisme d'événements pour l'app et les intégrations. |
| 13 | MCP : servi par le moteur (HTTP streamable `/mcp`) **+ shim stdio** qui relaie vers lui (modèle voicebox `mcp_shim`). | Une seule implémentation, un seul point de contrôle des permissions. |
