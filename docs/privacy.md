# Confidentialité : ce qui est garanti, comment le vérifier, ce qui ne l'est pas

## Ce que Hark fait pour rester local
| Couche | Mécanisme | Où |
|---|---|---|
| Moteur Python | **Garde réseau** : toute connexion / résolution DNS hors loopback lève `NetworkBlockedError` et est comptée | `engine/.../net/guard.py` |
| Moteur Python | Hugging Face reste hors ligne (`HF_HUB_OFFLINE=1`, télémétrie off) ; les modèles sont chargés avec `local_files_only` | `main.py`, `stt/` |
| Électron (Chromium) | Services d'arrière-plan coupés (`disable-component-update`, `disable-background-networking`…), proxy système ignoré, **tout nom d'hôte non local est irrésolvable**, et toute requête non locale est annulée et journalisée | `app/src/main/network.ts` |
| API | Écoute seulement sur `127.0.0.1` ; token dans le gestionnaire d'identifiants ; en-têtes `Host`/`Origin` contrôlés | `api/` |
| LLM | Ollama local, URL obligatoirement `127.0.0.1` ; cloud **désactivé**, activable seulement avec accusé + clé + sélection | `llm/` |

## Les seules sorties possibles (toutes sur clic explicite)
1. **Télécharger un modèle de transcription** (Réglages → Transcription) : depuis Hugging Face, aucune donnée envoyée.
2. **Télécharger un modèle Ollama** (Réglages → Analyse IA) : c'est **Ollama** qui télécharge, pas Hark.
3. **Fournisseur cloud** : si tu l'actives, le **texte** des transcriptions part vers le service choisi.
4. Un lien `http(s)` ouvert dans la fenêtre s'ouvre dans ton navigateur (aucun lien de ce type n'existe aujourd'hui).

## Comment le vérifier toi-même (Linux)
```bash
sudo apt-get install -y strace xvfb      # une fois
scripts/audit-network.sh
```
Le script lance **l'application réelle** (Électron + moteur) sur le scénario de bout en bout (enregistrement, transcription,
analyse, recherche, export) sous `strace` et **échoue** à la moindre connexion hors `127.0.0.1`, au moindre DNS, ou à
toute connexion vers un proxy (un proxy local mène à Internet). Il tourne aussi en CI.
Sur Windows/macOS : utilise un pare-feu sortant (ex. blocage de `Hark.exe`) ou Wireshark pendant un enregistrement.

## Ce qui n'est PAS garanti (honnêtement)
- **Cette garantie a été trouvée fausse une fois** : Chromium contactait `redirector.gvt1.com` (mises à jour de composants) à
  chaque lancement. Corrigé, et l'audit ci-dessus le détecte désormais. D'autres comportements d'Électron/Chromium sur
  **Windows** (ou une future version d'Électron) n'ont pas été mesurés : relance l'audit après chaque mise à jour d'Électron.
- La garde Python intercepte les connexions TCP et le DNS des sockets Python ; elle ne voit ni l'UDP sans `connect`, ni du
  code natif qui ouvrirait ses propres sockets. Le script d'audit (niveau noyau) comble ce trou **pour le scénario testé**.
- L'audit ne couvre pas les chemins qu'il n'exécute pas : vrai téléchargement de modèle, vrai Ollama, vrai faster-whisper.
- **Ollama** est un programme séparé, hors du contrôle de Hark. Il reste local tant que tu ne lui fais rien télécharger.
- L'installation (`pnpm install`, `uv sync`) et le lancement en développement (`uv run`) utilisent évidemment Internet ;
  ce n'est pas l'application installée.
- macOS : capture du son système non gérée dans cette version.
