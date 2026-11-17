# Gestion de formation

Sujet : systeme de gestion de formation en console (etudiants, formateurs, cours, inscriptions et evaluations) avec sauvegarde JSON.

## Participants

- BASTIEN Haggaï L.
- Aladin Scam

## Instructions de lancement

Ouvrir un terminal dans le dossier du projet, puis :

    python main.py data/demo.json

Avec les donnees de demonstration. Si la commande python ne fonctionne pas, essayer python3 (ou py sous Windows).

    python main.py

Sans argument, le programme utilise data/formation.json et le cree vide s'il est absent.

Autres commandes :

    python generer_demo.py
    python -m unittest discover -s tests -v

La premiere regenere data/demo.json (utile pour repartir de zero, car le programme modifie le fichier qu'il charge). La seconde lance les tests.

## Utilisation

Le programme affiche un menu numerote : taper un chiffre puis Entree. Menus disponibles : Personnes, Cours, Inscriptions, Evaluations, Tableaux de bord, Historique des operations. Le chiffre 0 permet de revenir en arriere ou de quitter.

## Fichiers

- main.py : menus console et tableaux de bord
- service.py : regles metier (conflits d'horaires, capacite, file d'attente, moyennes, statistiques)
- models.py : classes Personne, Etudiant, Formateur, Cours, Inscription, Evaluation, Creneau
- storage.py : chargement et sauvegarde JSON
- generer_demo.py : generation des donnees de demonstration
- tests/test_regles.py : tests unitaires
- data/demo.json : donnees de demonstration

## Regles metier

- Conflits d'horaires verifies avant toute inscription et toute assignation de formateur.
- Cours complet : inscription placee en liste d'attente. Apres un desistement, la place revient au premier candidat de la file sans conflit d'horaires.
- Note manquante : ignoree dans la moyenne (par defaut) ou comptee 0, au choix dans le menu Evaluations.
- Moyenne ponderee : somme des (note x coefficient) divisee par la somme des coefficients.
- Chaque operation est annulee entierement en cas d'erreur : aucune modification partielle.

## Sauvegarde JSON

Sauvegarde automatique apres chaque modification. Fichier absent : cree. Fichier invalide : le programme refuse de demarrer sans l'ecraser. Les identifiants restent uniques apres un redemarrage.
