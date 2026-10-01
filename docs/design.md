# Décisions et limites

## État plutôt que fichiers dispersés

Les contacts passent de `pending` à `drafted`, puis `simulated`. Une réponse ou
une opposition les place dans un état exclu des prochaines actions. Une adresse
réimportée ne réactive pas un contact opposé. Le journal porte le terme
`simulated`, jamais `sent`, car aucun message réel ne quitte cette démonstration.

## Règles explicites

La fenêtre du laboratoire est du lundi au vendredi, de 09:00 inclus à 17:00 exclu
**en UTC**. Ce choix rend les tests déterministes ; il ne constitue pas la
configuration du service privé. Une seule action peut être enregistrée par appel.
Les appels rapprochés sont refusés, sans faire attendre le programme.

Une transaction SQLite `BEGIN IMMEDIATE` commence avant les vérifications et
protège l'écriture locale. Une contrainte unique interdit de simuler deux premiers
messages à la même adresse. Le stockage est local : ce n'est pas une file
distribuée ou un mécanisme d'envoi garanti exactement une fois.

## Exclus volontairement

- Tout collecteur d'adresses et toute base de contacts réels.
- Le client Resend, les secrets et les configurations de compte.
- Les relances, webhooks, accusés de réception et automatisations système.
- Les promesses de conformité ou de délivrabilité.

Il faudrait valider séparément ces intégrations avant tout usage réel. En
particulier, enregistrer une opposition manuellement n'équivaut pas à traiter
automatiquement les réponses d'une boîte aux lettres.
