# Étape 2 — Détection de réunion + notification (sans enregistrement)

## Fait
- **Mesure du niveau** de la sortie système (`soundcard` : WASAPI loopback sous Windows, source `.monitor`
  PulseAudio/PipeWire sous Linux). On calcule un RMS en dBFS par bloc de 0,25 s ; **aucun échantillon n'est conservé**.
- **Signal « micro utilisé par une autre application »** : Linux via `pactl` (les flux qui lisent une source `.monitor`,
  Hark et `soundcard` sont ignorés) ; Windows via le registre `CapabilityAccessManager` ; macOS non géré (`null`).
- **Machine d'états** pure : `idle → (son ≥ seuil pendant N s ET micro utilisé) → prompted → cooldown | recording`.
  Les petites pauses de parole (≤ 2 s) ne remettent pas le compteur à zéro. Anti-spam : pause de 10 min après
  « ignorer »/absence de réponse, 30 min après « Non », aucune nouvelle demande pendant un enregistrement.
- **Notification de consentement** (petite fenêtre au premier plan, sans voler le focus) : « Réunion détectée —
  Enregistrer cette réunion ? », rappel « Pense à informer les participants », boutons **Enregistrer / Non**, barre de
  compte à rebours (20 s) ; la fermer ou ne rien faire = ignorer. `Échap` = ignorer.
- **Réglages → Détection** : jauge du niveau en direct avec le seuil, signal micro, état, seuil, durée, case
  « exiger le micro », bouton **Tester la notification**. Réglages persistés en SQLite (migration `0002_settings`).
- **Flux SSE** `GET /v1/events/stream` ; le kanban se rafraîchit maintenant en temps réel (`task.*`).
- Nouvelles routes : `GET /v1/detection/status`, `GET|PATCH /v1/settings/detection`, `POST /v1/detection/respond`,
  `POST /v1/detection/test`. Événement `meeting.detected` (avec `prompt_id`, `app`, `reminder`).
- Cliquer **Enregistrer** n'enregistre **rien** pour l'instant : Hark l'indique dans une notification
  (l'enregistreur arrive à l'étape 3 via `DetectorService.on_accept`).

## Tester à la main
```bash
git pull && pnpm install && (cd engine && uv sync) && pnpm --filter @hark/app dev:nosandbox
```
1. Kanban → **Réglages** → section « Détection des réunions » : la jauge bouge quand tu joues du son.
   Si elle affiche une erreur « Audio indisponible », suis le message (Linux : `libpulse`, PulseAudio/PipeWire-Pulse).
2. Clique **Tester la notification** : la fenêtre apparaît en bas à droite. **Non** → elle disparaît ; le statut passe à
   « En pause après ton choix ».
3. **YouTube seul** : lance une vidéo bruyante > 8 s → *aucune* notification (état « En écoute », micro : non).
4. **Appel** (Teams/Zoom/Meet) avec micro actif et du son > 8 s → la notification apparaît, avec le nom de l'application.
5. Pas de notification pendant un appel ? Regarde dans les réglages : niveau trop bas (baisse le seuil), ou « Micro
   utilisé : non/inconnu » (décoche « Exiger le micro » pour tester en mode audio seul).

## Limites
- macOS : pas de capture du son système ni de signal micro (version ultérieure).
- Un appel où le micro est coupé au niveau du système (flux fermé) n'est pas détecté tant qu'il n'est pas rouvert.
- La détection suit la sortie audio par défaut ; si elle change, l'écoute est rouverte (≈ 15 s).

## Correctif : « pas de notification alors que le son dépasse le seuil »
- Réglages → Détection affiche maintenant **« Pas de notification pour l'instant : … »** avec la raison exacte
  (micro non utilisé, durée pas atteinte, pause après un « Non », son sous le seuil, détection désactivée…) et la raison
  pour laquelle l'état du micro est illisible (ex. `pactl` introuvable → installe `pulseaudio-utils`).
- Si Hark **ne peut pas lire** l'état du micro, il ne bloque plus la notification (avant : jamais de notification).
  Il ne filtre que lorsqu'il sait qu'aucune application n'utilise le micro.
- La notification s'accompagne d'une **notification système** (clic = ramène la fenêtre au premier plan), au cas où la
  petite fenêtre serait masquée par ton bureau.
