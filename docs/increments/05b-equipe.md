# Étape 4b (partie 1) — Équipe et assignation des tâches

Demande : « Je suis lead, je dois faire le suivi des tâches de mon équipe : pouvoir assigner à une personne (Nom + Prénom + mail). »

## Fait
- **Annuaire d'équipe** (migration `0006_people`) : Prénom, Nom, e-mail (normalisé en minuscules, unique s'il est renseigné ;
  un prénom ou un nom est obligatoire). Routes `GET /v1/people` (read), `POST|PATCH|DELETE /v1/people/{id}` (ui).
- **Assignation** : `assignee_id` sur les tâches (création, modification, `null` pour désassigner) ; le moteur met le nom complet
  dans `assignee` (exports, plugins). Renommer une personne met à jour ses tâches ; la supprimer garde son nom en texte.
  T'assigner toi-même (même e-mail ou même nom que ton profil) marque la tâche « moi ».
- **Kanban** : filtre Toutes / Mes tâches / Non assignées / chaque membre (nombre de tâches ouvertes) ; pastille aux initiales
  sur les cartes ; une tâche créée en filtrant sur quelqu'un lui est assignée ; filtre mémorisé.
- **Éditeur de tâche** : liste des membres + « Ajouter une personne… » (Prénom, Nom, e-mail) sans quitter la tâche ; texte libre
  toujours possible sans personne.
- **IA** : l'assigné entendu (« Paul ») est relié à la personne s'il n'y a **qu'une** correspondance ; sinon rien n'est deviné.
- **Intégrations** : `POST /v1/tasks/propose` accepte `assignee_email` pour relier un membre existant (jamais en créer).
  `GET /v1/tasks?assignee_id=…` pour lister les tâches d'une personne. Contrat `Person` dans `/contracts`.

## Tester à la main
1. Réglages → **Équipe** : ajoute 2–3 personnes (et toi-même, avec l'e-mail de ton profil).
2. Ouvre une tâche → « Assigné à » → choisis quelqu'un, ou « + Ajouter une personne… ». La carte affiche ses initiales.
3. En haut du kanban, **Afficher** → un membre : seules ses tâches restent ; crée une tâche : elle lui est assignée.
4. Enregistre une réunion où « Paul, tu t'occupes du devis » : dans « À valider », la tâche est reliée à Paul (si un seul Paul).

## Limites
- Pas encore de reconnaissance des voix (qui parle sur la piste « Autres ») : c'est la suite de l'étape 4b.
- Pas de notification ni d'envoi d'e-mail aux personnes : Hark reste local, l'e-mail sert à identifier et à relier.
- Les intégrations avec le scope `read` voient les noms et e-mails de l'équipe (nécessaire pour leur suivi).
