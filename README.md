# Hark — assistant de réunion local

Hark est une application de bureau **locale** :

- un **kanban en panneau latéral** (à droite de l'écran, colonnes empilées et repliables) qui s'ouvre instantanément avec `Ctrl+Alt+K` ;
- **détection des réunions** (une notification te demande ; l'enregistrement viendra à l'étape 3, **uniquement après ton clic**), transcription
  locale (faster-whisper), résumé et proposition de tâches (Ollama) dans la colonne « À valider » ;
- un **historique** consultable et cherchable des réunions ;
- un écosystème ouvert : **API locale**, **serveur MCP**, **webhooks**, **plugins**, et un skill
  `plug-tools` pour brancher tes autres outils.

> L'assistant n'agit jamais à ta place : il observe, propose, et tu valides.

## État d'avancement

| Étape | Contenu | État |
|---|---|---|
| 1 | Squelette Electron + moteur, tray, raccourci, kanban persistant | ✅ |
| 2 | Détection audio + notification de consentement (sans enregistrement) | ✅ |
| 3 | Enregistrement deux pistes + fin de réunion | ✅ |
| 4 | Transcription locale + historique + recherche + export Markdown | ✅ |
| 4b | Équipe (Prénom, Nom, mail) + assignation + filtre par personne | ✅ |
| 4c | Voix → personnes (reconnaissance des voix) | ⏳ |
| 5 | Analyse LLM + « À valider » + profil + budget tokens | ✅ |
| 6 | API locale complète + webhooks + MCP + plugin d'exemple | ⏳ |
| 7 | Skill `plug-tools` + templates + `scripts/check-plugin` | ⏳ |

Notes par étape : [`docs/increments/`](docs/increments/).

## Installation (développement)

Prérequis : Node 20+, [pnpm](https://pnpm.io) 10 (`npm install -g pnpm`) et
[uv](https://docs.astral.sh/uv/) (installe aussi Python 3.11+ tout seul) :

```bash
# Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```
```powershell
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

```bash
pnpm install
(cd engine && uv sync)
pnpm dev
```

Systèmes : **Windows et Linux** pour le MVP. macOS : l'interface fonctionne, la capture du son
système arrivera dans une version ultérieure.

Linux : si Electron s'arrête avec « The SUID sandbox helper binary was found, but is not configured
correctly », fais une fois `sudo chown root:root` puis `sudo chmod 4755` sur
`node_modules/.pnpm/electron@*/node_modules/electron/dist/chrome-sandbox`, ou (dev uniquement) lance
`pnpm --filter @hark/app dev:nosandbox`.

Linux : l'icône de zone de notification nécessite un support AppIndicator (sous GNOME, l'extension
« AppIndicator and KStatusNotifierItem Support »). Sous Wayland, le raccourci global passe par le portail
XDG ; ton bureau peut te demander de le confirmer.

## Détection des réunions

Hark mesure le **niveau** du son sortant du PC (jamais enregistré) et demande à enregistrer quand une
réunion est probable : son au-dessus du seuil pendant N secondes (défaut 8) **et** une autre application
utilise le micro (c'est ce qui distingue un appel Teams/Zoom/Meet d'une vidéo YouTube).
La notification (Enregistrer / Non) disparaît seule après 20 s, ce qui équivaut à ignorer.
Après « Non » ou une absence de réponse, Hark se tait pendant 30 min / 10 min.
Réglages → « Détection des réunions » : jauge de niveau en direct, seuil, durée, bouton « Tester la notification ».

Prérequis Linux : PulseAudio ou PipeWire (avec `pipewire-pulse`), la bibliothèque `libpulse`, et la commande `pactl`
(paquet `pulseaudio-utils`). Windows : rien à installer. macOS : non pris en charge dans cette version.

## Enregistrement

Il ne démarre **que sur ton clic** : « Enregistrer » dans la notification, « ● Enregistrer » dans le kanban, ou
« Démarrer un enregistrement » dans le menu de l'icône. Pendant l'enregistrement : icône rouge dans la zone de
notification, petite fenêtre « REC » toujours au premier plan (durée, titre facultatif, **■ Stop**), et un bouton Stop
dans le kanban. Deux pistes WAV 16 kHz sont écrites dans le dossier de données (`audio/<id>/system.wav` = les autres,
`mic.wav` = toi) ; si le micro est introuvable, la piste système est enregistrée seule, avec un avertissement.

Après 3 min de silence (réglable) sur les deux pistes, « Réunion terminée ? » s'affiche et **reste** jusqu'à ce que
quelqu'un reparle (elle disparaît alors) ou que tu choisisses Arrêter / Continuer. Hark ne s'arrête jamais seul.
Si tu quittes Hark ou si l'ordinateur plante pendant un enregistrement, ce qui était déjà écrit est conservé.

## Transcription et historique

À la fin d'un enregistrement, Hark transcrit **localement** avec faster-whisper (piste micro = « Moi », piste système =
« Autres »), avec horodatage par segment, en français et en anglais (détection automatique, ou langue imposée).
**Premier lancement : il faut télécharger un modèle** (Réglages → Transcription) ; choisis selon ta machine :

| Profil | Modèle | Taille | Pour |
|---|---|---|---|
| Léger | base | ≈ 150 Mo | petit PC, 4 Go de RAM |
| Équilibré | small | ≈ 490 Mo | portable récent sans GPU (recommandé par défaut) |
| Précis | medium | ≈ 1,5 Go | 16 Go de RAM, idéalement GPU NVIDIA |
| Très précis | large-v3-turbo | ≈ 1,6 Go | GPU NVIDIA ≥ 6 Go de VRAM |

Le téléchargement (depuis Hugging Face, **aucune donnée envoyée**) est la **seule** connexion réseau du moteur et ne se fait
que si tu cliques. Le reste du moteur est protégé par une garde qui refuse toute connexion hors `127.0.0.1`.
**Audio supprimé après transcription réussie** par défaut (réglable : 7 ou 30 jours). Si la transcription échoue ou si le
modèle manque, l'audio est conservé et la réunion attend.

Onglet **Réunions** : liste (date, durée, titre, nombre de tâches, état), recherche plein texte (titres et transcriptions,
insensible aux accents, préfixes), page détail avec transcription horodatée, titre modifiable, **export Markdown**,
retranscription, suppression.

## Analyse (résumé, décisions, tâches)

Après la transcription, Hark analyse la réunion avec un **LLM local (Ollama)** : résumé (≤ 10 lignes), décisions, tâches
(titre, assigné, échéance, confiance, extrait horodaté), questions ouvertes, et un titre si tu n'en as pas mis.
**Toutes les tâches arrivent dans « À valider »** ; celles qui te concernent sont en tête (assigné = toi d'après ton
`profile.yaml`, ou « je m'en occupe » dit sur ta piste micro). Chaque tâche renvoie à l'extrait de transcription d'origine.

Installation : [Ollama](https://ollama.com), puis Réglages → **Analyse IA** → choisis un modèle (Léger 3B / Équilibré 7B /
Précis 14B selon ta machine, ou n'importe quel modèle déjà installé) et clique Télécharger (c'est Ollama qui télécharge).

**Maîtrise des tokens** : transcription découpée en blocs → un résumé par bloc → **une seule** passe finale d'extraction ;
budget maximum par réunion (refus avant tout envoi s'il est dépassé) ; une même transcription (même modèle, même profil)
n'est **jamais** ré-analysée (cache par hash). Seul un clic sur « Ré-analyser » force un nouvel appel.

**Fournisseur cloud** : désactivé par défaut. Il ne s'active que si tu coches explicitement que le texte de tes réunions
quittera ta machine, fournis une clé (rangée dans le gestionnaire d'identifiants) et le sélectionnes.

## Le panneau

`Ctrl+Alt+K` fait glisser Hark depuis la droite de l'écran où se trouve ta souris (toute la hauteur, au-dessus des autres
fenêtres) ; `Échap`, × ou **un clic ailleurs** le masque. Le bouton 📌 (ou Réglages → « Masquer le panneau quand je clique
ailleurs ») l'épingle pour qu'il reste affiché pendant que tu travailles. Les quatre colonnes sont **empilées** ; clique sur un en-tête (À valider, À faire,
En cours, Fait) pour le **replier/déplier** : ton choix est mémorisé, et une colonne repliée accepte toujours qu'on y dépose
une tâche. Le style (surfaces chaudes, accent terracotta, thème clair/sombre automatique) reprend celui d'[aska](https://github.com/JunsyG92/aska).

## Équipe et suivi des tâches

Réglages → **Équipe** : la liste des personnes de ton équipe (Prénom, Nom, e-mail ; une adresse = une personne).
Dans une tâche, « Assigné à » propose ces personnes, ou « + Ajouter une personne… » pour la créer à la volée.
Le kanban se filtre en haut : **Toutes / Mes tâches / Non assignées / chaque membre** (avec son nombre de tâches ouvertes) ;
une tâche créée pendant que tu filtres sur quelqu'un lui est assignée. Quand l'IA entend un prénom qui correspond à **une
seule** personne de la liste, la tâche lui est reliée (toujours dans « À valider ») ; en cas d'ambiguïté, rien n'est deviné.
Mets-toi aussi dans la liste avec l'e-mail de ton profil : ce qui t'est assigné est alors marqué « moi ».
Les intégrations peuvent relier une tâche proposée à un membre existant via `assignee_email` (jamais en créer).

## Configuration

- **Raccourci** et **lancement au démarrage** : bouton « Réglages » du kanban ou menu de l'icône.
- **Dossier de données** : variable `HARK_DATA_DIR`, sinon
  `~/.local/share/Hark` (Linux), `%LOCALAPPDATA%\Hark` (Windows).
- **Port de l'API** : `HARK_PORT` (défaut 47821, sinon un port libre). Le port courant est écrit dans
  `runtime.json` du dossier de données.

## Confidentialité

> Détails, limites et **script de vérification** : [`docs/privacy.md`](docs/privacy.md) (`scripts/audit-network.sh`).

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
pnpm --filter @hark/app build && xvfb-run -a -s "-screen 0 1600x1000x24" pnpm --filter @hark/app e2e   # smoke test de l'app réelle
```

Architecture : [`docs/architecture.md`](docs/architecture.md) · Décisions : [`docs/decisions.md`](docs/decisions.md)
· Contrats : [`contracts/`](contracts/).
