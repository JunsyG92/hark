# Progression (gamification) — jour / mois / année

## Fait
- **Moteur** : journal `activity` (migration `0007`) alimenté par les déplacements de tâches : tâche terminée (points),
  proposition de l'IA traitée (2 points). Une tâche n'est créditée qu'une fois ; la sortir de « Fait » retire ses points.
  Points : 10 par tâche à toi, +5 avant l'échéance, +5 priorité haute ; tâches de l'équipe sans points.
  Niveaux (niveau n à partir de 50·(n−1)² XP), séries (aujourd'hui sans activité ne casse pas la série d'hier), 11 badges,
  objectif quotidien réglable. `GET /v1/progress[?month=YYYY-MM&year=YYYY]`, `GET|PATCH /v1/settings/progress`.
  Les tâches déjà terminées avant cette version sont importées dans l'historique **sans** points.
- **Interface** : onglet **Progrès** — niveau + barre d'XP + série ; **Jour** (anneau d'objectif, points, tâches terminées),
  **Mois** (stats, comparaison, calendrier coloré selon l'objectif, équipe par ordre alphabétique, navigation),
  **Année** (stats, carte de chaleur, meilleur mois, navigation) ; badges avec progression ; célébration à chaque tâche
  terminée ; Réglages → Progression (activer, objectif). Le bouton d'enregistrement de l'en-tête devient une pastille
  compacte pour laisser la place au 3ᵉ onglet.

## Tester à la main
1. Glisse une de tes tâches dans « Fait » : « +10 pts · Objectif du jour : 1/3 » s'affiche.
2. Onglet **Progrès** → Jour / Mois / Année. Remets la tâche dans « À faire » : les points disparaissent.
3. Assigne une tâche à un membre de l'équipe et termine-la : pas de points pour toi, elle apparaît dans « Équipe ce mois-ci ».
4. Réglages → Progression : change l'objectif, ou désactive (l'onglet disparaît).

## Limites
- Les jours sont ceux de l'heure locale de la machine au moment de l'action ; l'historique importé utilise la date UTC
  de dernière modification (approximatif).
- Pas de « congés » : un jour sans tâche casse la série.
