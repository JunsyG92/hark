# Étape 4 — Transcription locale, historique, recherche, export

## Fait
- **Transcription locale** (faster-whisper) lancée automatiquement à la fin d'un enregistrement (réglable) : file
  d'attente (une réunion à la fois), VAD pour ignorer les silences, langue `auto` (choix entre français et anglais),
  `fr` ou `en`. Piste micro → « Moi », piste système → « Autres », segments horodatés triés dans le temps.
- **Profils de modèles** (Léger / Équilibré / Précis / Très précis) avec recommandation selon la RAM et la présence d'un
  GPU, et **téléchargement explicite** depuis Réglages → Transcription. Sans modèle, la réunion reste « en attente d'un
  modèle » (audio conservé) et repart toute seule après l'installation.
- **Rétention de l'audio** : supprimé dès la transcription réussie (défaut), ou conservé 7 / 30 jours (purge toutes les
  heures). Un échec de transcription garde l'audio ; « Transcrire / Retranscrire » relance.
- **Historique** (onglet Réunions) : liste (date, durée, titre, nb de tâches, état), détail avec transcription
  horodatée, titre modifiable, tâches liées, suppression (transcription + audio + index).
- **Recherche plein texte SQLite FTS5** (titres + transcriptions) : insensible aux accents et à la casse, préfixes,
  extraits avec mots surlignés, clic = ouvre la réunion à l'endroit trouvé.
- **Export Markdown** (`GET /v1/meetings/{id}/export.md`, bouton « Exporter en Markdown ») : titre, date, durée, langue,
  tâches liées, transcription horodatée avec « Moi / Autres ».
- **Garde réseau** : le moteur refuse toute connexion hors `127.0.0.1` (sauf le téléchargement de modèle demandé).
- Routes : `GET /v1/search`, `GET /v1/meetings/{id}/transcript|export.md`, `DELETE|POST …/transcribe`, `GET /v1/models`,
  `POST /v1/models/download`, `GET|PATCH /v1/settings/transcription`, `GET /v1/transcription/status`.
  Événement `transcript.ready`. Contrats : `Meeting` (+ état de transcription, langue, nb de tâches), `TranscriptSegment`,
  `SearchHit`, `ModelProfile`, `TranscriptionSettings`.

## Tester à la main
```bash
git pull && pnpm install && (cd engine && uv sync) && pnpm --filter @hark/app dev:nosandbox
```
1. Réglages → **Transcription** : choisis un profil (le recommandé est indiqué) et clique **Télécharger**. Seul clic
   qui ouvre une connexion réseau.
2. Enregistre quelques minutes de **vraie** conversation (toi + une vidéo ou un appel), puis **■ Stop**. La réunion
   apparaît dans **Réunions** : « transcription en cours… » puis « transcription prête » + notification.
3. Ouvre-la : lis la transcription (« Autres » = sortie système, « Moi » = micro). Cherche un mot entendu (avec ou sans
   accent) dans la barre de recherche ; clique un résultat.
4. **Exporter en Markdown**, ouvre le fichier. Vérifie que l'audio a disparu de `audio/` (rétention par défaut).
5. Mets la rétention à 7 jours, refais un enregistrement : l'audio reste, et **Retranscrire** fonctionne.

## Limites
- **Écho** : sans casque, le micro capte aussi le haut-parleur ; une phrase peut alors apparaître côté « Moi » ET « Autres ».
  (Atténuation d'écho non incluse dans le MVP : utilise un casque pour une attribution propre.)
- Pas de séparation des voix de la piste « Autres » : c'est l'étape **4b** (voix → personnes, nom + mail).
- Le vrai chemin faster-whisper (téléchargement + chargement + transcription d'un modèle réel) n'a pas pu être exécuté
  dans l'environnement de développement (réseau vers Hugging Face bloqué) : lance
  `HARK_TEST_REAL_STT=1 uv run pytest tests/test_real_stt.py -s` pour le vérifier chez toi.
- Une réunion de 30 min prend de quelques minutes (GPU / modèle léger) à plusieurs dizaines de minutes (CPU, modèle précis).

## Correctif (après premier essai réel)
- `TypeError: open() got an unexpected keyword argument 'metadata_errors'` : PyAV 19 a retiré une option que le décodeur
  de faster-whisper 1.2.1 lui passe. Hark lit maintenant lui-même ses WAV 16 kHz (`soundfile`) et donne le signal à
  faster-whisper, sans passer par PyAV/ffmpeg. Test de non-régression avec un faux modèle (`test_faster_whisper_receives_a_float32_array_not_a_file_path`).
- Les réunions déjà enregistrées gardent leur audio : ouvre la réunion → **Transcrire** (ou **Retranscrire**).
