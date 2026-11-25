# Étape 3 — Enregistrement deux pistes + fin de réunion

## Fait
- **Enregistreur** (`engine/.../record/`) : deux pistes (`system` = sortie système / les autres, `mic` = toi) écrites en
  **WAV 16 kHz mono** dans `audio/<id>/`. Jamais lancé sans action explicite de l'utilisateur (scope `ui`).
  Piste manquante (ex. pas de micro) → l'autre piste est enregistrée avec un avertissement ; aucun périphérique → erreur
  claire, rien n'est créé.
- **Réunions en base** (migration `0003_meetings`) : `GET /v1/meetings`, `GET /v1/meetings/{id}`,
  `PATCH /v1/meetings/{id}` (titre). Contrat `Meeting` dans `/contracts`.
- **Routes** : `GET /v1/recording/status` (durée, niveaux des deux pistes, silence), `POST /v1/recording/start|stop`,
  `GET|PATCH /v1/settings/recording`. Événements `meeting.recording_started`, `meeting.recorded`, `meeting.silence`.
- **Indicateurs de consentement** : icône de la zone de notification rouge ; fenêtre « REC » toujours au premier plan
  (durée, **titre facultatif**, **■ Stop**, non fermable pendant l'enregistrement) ; barre REC + Stop dans le kanban ;
  rappel « Pense à informer les participants » (notification de détection et démarrage manuel).
- **Fin de réunion** : silence ≥ 3 min (réglable) sur *les deux* pistes → notification « Réunion terminée ? »
  [Arrêter] [Continuer]. Elle **reste affichée** jusqu'à ce qu'une voix revienne (elle disparaît seule) ou que tu
  répondes ; « Continuer » la repose après un nouveau délai de silence. **Aucun arrêt automatique.**
- **Robustesse** : quitter Hark pendant un enregistrement le finalise (l'app attend le moteur) ; après un crash, le
  démarrage suivant referme la réunion avec l'audio déjà écrit (≤ 0,25 s perdue).
- Détection : plus de nouvelle proposition pendant un enregistrement ; pause de 10 min après l'arrêt.

## Tester à la main
```bash
git pull && pnpm install && (cd engine && uv sync) && pnpm --filter @hark/app dev:nosandbox
```
1. Clique **● Enregistrer** (kanban) : la fenêtre REC apparaît en haut à droite, l'icône devient rouge. Tape un titre
   dans la fenêtre REC puis Entrée.
2. Réglages → « Enregistrement » : tant que tu parles et qu'une vidéo/réunion joue, les niveaux **système** et **micro**
   bougent. Si le niveau « micro » reste « — », le micro n'est pas capté (le message d'avertissement l'indique).
3. **■ Stop** (fenêtre REC, kanban ou menu de l'icône). Vérifie dans le dossier de données `audio/<id>/` : `system.wav`
   et `mic.wav` s'ouvrent dans un lecteur audio (système = les autres, micro = ta voix).
   Dossier : Linux `~/.local/share/Hark/audio`, Windows `%LOCALAPPDATA%\Hark\audio`.
4. Fin de réunion : mets « minutes de silence » à 1 et le seuil de silence au-dessus de ton bruit de fond, reste muet
   1 min → « Réunion terminée ? » apparaît et reste ; parle → elle disparaît ; ou clique Arrêter.
5. Quitte Hark (menu de l'icône) pendant un enregistrement, relance : la réunion existe (`GET /v1/meetings`) et ses
   fichiers sont lisibles.

## Limites
- Le micro d'ordinateur a souvent un bruit de fond > -45 dB : si « Réunion terminée ? » ne vient jamais, monte le
  seuil de silence (Réglages → Enregistrement, les niveaux en direct t'aident).
- Les deux pistes sont enregistrées en parallèle sans recalage explicite (dérive négligeable sur quelques heures).
- Windows : capture (WASAPI) et registre micro non testés ici (CI Windows pour la partie logicielle).
- La transcription, l'historique détaillé et la suppression de l'audio arrivent à l'étape 4.
