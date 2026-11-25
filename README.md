# Hark — assistant de réunion local

Hark est une application de bureau **locale** :

- un **kanban** qui s'ouvre instantanément avec `Ctrl+Alt+K` ;
- (à venir) **détection des réunions**, puis enregistrement **uniquement après ton clic**, transcription
  locale (faster-whisper), résumé et proposition de tâches (Ollama) dans la colonne « À valider » ;
- un **historique** consultable et cherchable des réunions ;
- un écosystème ouvert : **API locale**, **serveur MCP**, **webhooks**, **plugins**, et un skill
  `plug-tools` pour brancher tes autres outils.

> L'assistant n'agit jamais à ta place : il observe, propose, et tu valides.

## État d'avancement

| Étape | Contenu | État |
|---|---|---|
| 1 | Squelette Electron + moteur, tray, raccourci, kanban persistant | ✅ |
| 2 | Détection audio + notification | ⏳ |
| 3 | Enregistrement deux pistes + fin de réunion | ⏳ |
| 4 | Transcription locale + historique + recherche (4b : voix → personnes) | ⏳ |
| 5 | Analyse LLM + « À valider » + profil + budget tokens | ⏳ |
| 6 | API locale complète + webhooks + MCP + plugin d'exemple | ⏳ |
| 7 | Skill `plug-tools` + templates + `scripts/check-plugin` | ⏳ |

Notes par étape : [`docs/increments/`](docs/increments/).

## Installation (développement)

Prérequis : Node 20+, [pnpm](https://pnpm.io) 10, [uv](https://docs.astral.sh/uv/), Python 3.11+.

```bash
pnpm install
(cd engine && uv sync)
pnpm dev
```

Systèmes : **Windows et Linux** pour le MVP. macOS : l'interface fonctionne, la capture du son
système arrivera dans une version ultérieure.

Linux : l'icône de zone de notification nécessite un support AppIndicator (sous GNOME, l'extension
« AppIndicator and KStatusNotifierItem Support »). Sous Wayland, le raccourci global passe par le portail
XDG ; ton bureau peut te demander de le confirmer.

## Configuration

- **Raccourci** et **lancement au démarrage** : bouton « Réglages » du kanban ou menu de l'icône.
- **Dossier de données** : variable `HARK_DATA_DIR`, sinon
  `~/.local/share/Hark` (Linux), `%LOCALAPPDATA%\Hark` (Windows).
- **Port de l'API** : `HARK_PORT` (défaut 47821, sinon un port libre). Le port courant est écrit dans
  `runtime.json` du dossier de données.

## Confidentialité

- **Rien ne quitte ta machine par défaut.** Pas de télémétrie. Transcription et LLM locaux.
  Un fournisseur LLM cloud existera, **désactivé par défaut**, activable seulement par configuration explicite.
- **Consentement** : aucun enregistrement sans clic explicite ; indicateur rouge permanent pendant
  l'enregistrement, bouton Stop toujours accessible ; rappel « Pense à informer les participants ».
- **Audio supprimé après transcription réussie** par défaut (rétention 0 / 7 / 30 jours configurable).
- **API locale** : écoute sur `127.0.0.1` seulement, token généré au premier lancement et rangé dans le
  gestionnaire d'identifiants de l'OS (service `hark`, compte `api-token`). Les requêtes venant d'un
  navigateur (en-tête `Origin`) ou d'un autre nom d'hôte sont refusées.
- **Intégrations en lecture seule par défaut** : elles peuvent lire et *proposer* des tâches (qui
  arrivent dans « À valider »), jamais modifier ni supprimer.

## Développement

```bash
scripts/check.sh            # lint + tests (Python et TypeScript)
pnpm --filter @hark/app build && xvfb-run -a pnpm --filter @hark/app e2e   # smoke test de l'app réelle
```

Architecture : [`docs/architecture.md`](docs/architecture.md) · Décisions : [`docs/decisions.md`](docs/decisions.md)
· Contrats : [`contracts/`](contracts/).
