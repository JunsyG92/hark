# Panneau latéral dans le style d'aska

Demande : « un design dans le même style qu'aska, dans un side panel qui s'ouvre sur la droite, les colonnes les unes sur
les autres et rétractables comme un collapse ».

## Fait
- **Panneau latéral droit** : fenêtre sans cadre, transparente autour d'une surface arrondie (18 px) avec ombre, toute la
  hauteur de l'écran où se trouve la souris, au premier plan ; entrée glissée depuis la droite (désactivée si « réduire les
  animations » est demandé par le système). `Ctrl+Alt+K` ouvre/ferme, `Échap` ou × masque. Toujours < 300 ms (fenêtre
  pré-chargée).
- **Colonnes empilées et repliables** : en-tête cliquable (chevron, nombre de tâches, « N pour toi » dans À valider),
  `aria-expanded`, état mémorisé ; une colonne repliée reste une zone de dépôt pour le glisser-déposer. `N` déplie
  « À faire » si besoin avant d'y écrire.
- **Style aska** : surfaces chaudes `#fbfaf8` / `#1d1d20`, accent terracotta `#d97757`, en-têtes en petites capitales, cartes
  type « historique » (barre d'accent à gauche pour tes tâches), pied de page avec raccourcis en `kbd`, thème clair/sombre
  automatique. Notification de consentement et fenêtre REC harmonisées.
- **Réunions** en navigation liste → détail (« ‹ Réunions » pour revenir), recherche en tête de liste.
- Le rappel « Pense à informer les participants » s'affiche en bulle après un démarrage manuel.

## Tester à la main
`Ctrl+Alt+K` → le panneau glisse depuis la droite. Replie « Fait », ferme et rouvre Hark : il reste replié. Glisse une
tâche sur l'en-tête replié de « Fait » : elle y est déposée. Change le thème du système : le panneau suit.

## Limites
- Sous Linux, la transparence demande un compositeur (GNOME, KDE… l'ont) ; sans compositeur, les coins arrondis
  apparaissent sur fond noir.
- La largeur est fixe (460 px) ; pas encore de redimensionnement ni de choix du côté (gauche/droite).

## Ajout : masquage au clic extérieur
- Un clic sur une autre fenêtre masque le panneau (comme aska). Il reste affiché s'il est **épinglé** (bouton 📌 dans l'en-tête,
  ou Réglages → « Masquer le panneau quand je clique ailleurs »), pendant une boîte de dialogue de Hark (export Markdown,
  confirmations de suppression, désormais natives), avec les devtools ouverts, et juste après l'ouverture.
- Garde-fou : si le pointeur est **dans** le panneau au moment de la perte de focus (liste déroulante, calendrier), il ne se
  masque pas. Sous Openbox, ces listes ne prennent pas le focus (vérifié) : ce garde-fou vise les bureaux où elles le prennent
  et n'a pas pu être démontré ici.
- Test réel au clic sous gestionnaire de fenêtres (Openbox + xdotool) : `scripts/e2e-outside-click.sh` (aussi en CI).
