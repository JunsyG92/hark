# Étape 5 — Analyse LLM, tâches « À valider », profil, budget de tokens

## Fait
- **Couche fournisseur** `LLMProvider` : `OllamaProvider` (défaut, serveur local, URL imposée en loopback),
  `CloudProvider` (OpenAI-compatible) **désactivé par défaut** et activable seulement avec accusé explicite + clé (gestionnaire
  d'identifiants) + sélection ; fournisseur factice pour les tests.
- **Pipeline** : transcription → lignes `[mm:ss] Moi/Autres: …` → blocs (≤ 1500 tokens, réglable) → un résumé par bloc →
  une passe finale d'extraction en JSON (`title`, `summary` ≤ 10 lignes, `decisions[]`, `tasks[]` {titre, assigné, échéance,
  confiance, horodatage de l'extrait}, `open_questions[]`), **validée par schéma** (un essai de réparation, sinon échec explicite).
  Un seul bloc ⇒ pas d'étape de résumé (moins de tokens).
- **Budget** : estimation pessimiste avant tout envoi (refus si > budget, aucun appel), comptage réel pendant ; défaut 40 000
  tokens/réunion, réglable. **Cache par hash** : même transcription + modèle + profil + prompts ⇒ aucun appel ; l'analyse
  automatique ne retraite jamais une réunion déjà analysée ; « Ré-analyser » force et ne duplique pas les tâches.
- **Tâches** : créées via `propose` ⇒ **toujours « À valider »**, avec source `meeting:<id>`, extrait horodaté (lien « voir
  l'extrait » → ouvre la réunion au bon passage), confiance, et l'extrait cité dans la description. **Mes tâches en tête** et
  marquées « moi » : assigné = ton nom/surnom (`profile.yaml`) ou « moi/je », ou « je m'en occupe »-like dit sur ta piste micro.
- **Profil** `profile.yaml` (nom, surnoms, rôle, équipe, projets, mots-clés) éditable dans Réglages → Analyse IA ; YAML sûr,
  validé (une erreur n'écrit rien) ; fait partie du hash du cache.
- **Résumé dans l'historique** : détail d'une réunion (résumé, décisions, questions ouvertes, tokens utilisés), résumé indexé
  dans la recherche, titre automatique si tu n'en as pas mis, état « analysée / en attente du LLM / échec » dans la liste.
- Événement `analysis.ready` ; notification « Analyse terminée : N tâches à valider ».
- Routes : `GET /v1/meetings/{id}/analysis`, `POST …/analyze[?force]`, `GET /v1/analysis/status`, `GET|PATCH /v1/settings/llm`,
  `GET /v1/llm/models`, `POST /v1/llm/pull`, `GET|PATCH /v1/settings/cloud`, `PUT /v1/settings/cloud/key`, `GET|PUT /v1/profile`.

## Tester à la main
```bash
git pull && pnpm install && (cd engine && uv sync) && pnpm --filter @hark/app dev:nosandbox
```
1. Installe [Ollama](https://ollama.com) et lance-le. Réglages → **Analyse IA** : le statut doit passer à « Prêt » ;
   choisis un modèle (le recommandé est indiqué) et **Télécharger** si besoin (c'est Ollama qui télécharge).
2. Complète ton **profil** (nom + surnoms) et enregistre-le (une erreur YAML s'affiche sans rien casser).
3. Enregistre une réunion où tu dis « je m'en occupe » et où quelqu'un d'autre se voit confier une tâche. Après la
   transcription, l'analyse démarre seule : **Réunions** → résumé, décisions, questions ouvertes ; **Kanban → À valider** :
   tes tâches sont en tête, marquées « moi ». Ouvre une tâche → **voir l'extrait**.
4. Clique **Analyser** deux fois de suite : le 2ᵉ clic ne consomme rien (mêmes `tokens` affichés, pas de nouveau calcul).
5. Arrête Ollama puis analyse une réunion : l'état devient « en attente du LLM » avec la raison ; relance Ollama et
   enregistre un réglage (ou clique Analyser) : elle repart.

## Limites
- **Ollama réel non exécuté en développement** (pas disponible dans l'environnement) : le contrat HTTP est testé contre un faux
  serveur local ; la qualité d'extraction dépend du modèle choisi (un 3B rate des tâches, le 7B est le minimum conseillé).
- La qualité de l'attribution « moi / autres » reste celle des pistes (écho sans casque, étape 4).
- Pas de détection de doublons entre réunions différentes, ni de fusion avec tes tâches existantes.
- Le fournisseur cloud est un squelette fonctionnel contre une API OpenAI-compatible, non testé contre un vrai service.

## Correctif : « transcription OK mais pas de bouton pour analyser »
- La vue détail n'affichait pas l'état de l'analyse et masquait le bouton pendant qu'elle tournait : on ne voyait rien.
  Désormais : état dans l'en-tête de la réunion, bouton toujours présent (grisé « Analyse en cours… »), bandeau
  « étape n/N » pendant que le LLM travaille.
- Une analyse ou une transcription interrompue (app fermée / plantage) restait bloquée « en cours » pour toujours.
  Au démarrage, ce travail repasse « en attente » et est relancé automatiquement (tests de non-régression).
