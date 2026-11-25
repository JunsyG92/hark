# Architecture

```
┌──────────────────── Electron (main) ────────────────────┐
│ Tray (rouge si REC) · Global shortcut · Mini-overlay REC │
│ Toast consentement · Cycle de vie du sidecar · Proxy IPC │
│   └─ Renderer React : Kanban · Historique · Réglages     │
└──────────────┬──── HTTP 127.0.0.1 + Bearer (main only) ──┘
               │
┌──────────────▼──────────── Engine Python ───────────────────────────┐
│ api/       FastAPI, scopes ui | read | propose, garde loopback      │
│ events.py  bus interne ─► (SSE, webhooks HMAC : étape 6)            │
│ store/     SQLite + migrations versionnées (+ FTS5 : étape 4)       │
│ audio/  niveau RMS de la sortie système (loopback, rien stocké)     │
│ detect/ machine d'états + sondes "micro utilisé" + service (thread) │
│ record/ (étape 3) · stt/ voices/ (4, 4b)                            │
│ analysis/ llm/ profile/ (étape 5) · plugins/ mcp (étape 6)          │
└─────────────────────────────────────────────────────────────────────┘
```

## Démarrage

1. Electron lance `hark-engine --sidecar` (dev : `uv run --project engine`).
2. Le moteur choisit son port (47821 par défaut, sinon un port libre), écrit
   `runtime.json` (port + pid, **jamais le token**) dans le dossier de données et
   imprime une ligne JSON `{"event":"ready","port":…,"token":…}` sur stdout.
3. Electron garde le token en mémoire dans le process main. Le renderer appelle
   `window.hark.api({method, path, body})` → IPC → main → HTTP loopback.
4. Si Electron meurt, stdin du moteur se ferme → le moteur s'arrête.

## Permissions

| Scope | Qui | Droits |
|---|---|---|
| `ui` | l'app de bureau (token maître) | tout |
| `read` | intégrations, MCP | lire réunions, tâches, transcriptions, recherche |
| `propose` | intégrations, MCP | `POST /v1/tasks/propose` → toujours « À valider » |

Les tokens scopés par plugin arrivent à l'étape 6.

## Dossier de données

`HARK_DATA_DIR` ou, par défaut (platformdirs) :
Linux `~/.local/share/Hark`, Windows `%LOCALAPPDATA%\Hark`, macOS `~/Library/Application Support/Hark`.
Contient `hark.sqlite3`, `audio/`, `runtime.json`.
