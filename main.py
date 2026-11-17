from __future__ import annotations

import sys
from pathlib import Path

from models import CONFIRMEE, EN_ATTENTE, Creneau, ErreurFichier, ErreurMetier
from service import POLITIQUES_NOTES, Systeme
from storage import charger

CHEMIN_DEFAUT = Path("data/formation.json")


def lire_texte(msg: str, obligatoire: bool = True) -> str:
    while True:
        s = input(msg).strip()
        if s or not obligatoire:
            return s
        print("  Champ obligatoire.")


def lire_nombre(msg: str, mini=None, maxi=None, entier=False):
    while True:
        brut = input(msg).strip().replace(",", ".")
        try:
            n = int(brut) if entier else float(brut)
        except ValueError:
            print("  Entrez un nombre" + (" entier." if entier else "."))
            continue
        if (mini is not None and n < mini) or (maxi is not None and n > maxi):
            print(f"  Valeur attendue entre {mini} et {maxi}.")
            continue
        return n


def choisir(msg: str, items: list, libelle):
    if not items:
        raise ErreurMetier("Aucun element disponible.")
    for k, it in enumerate(items, 1):
        print(f"  {k}. {libelle(it)}")
    n = lire_nombre(f"{msg} (0 = annuler) : ", 0, len(items), entier=True)
    return None if n == 0 else items[n - 1]


def lire_creneaux() -> list[Creneau]:
    print("Creneaux (ex : lundi 08:00-10:00). Ligne vide pour terminer.")
    creneaux = []
    while True:
        t = input("  Creneau : ").strip()
        if not t:
            if creneaux:
                return creneaux
            print("  Au moins un creneau.")
            continue
        try:
            creneaux.append(Creneau.parse(t))
        except ErreurMetier as e:
            print(f"  Erreur {e}")


def l_etu(e): return f"{e.id}  {e.nom_complet}  {e.filiere}".rstrip()
def l_for(f): return f"{f.id}  {f.nom_complet}  {f.specialite}".rstrip()
def l_cours(c):
    f = c.formateur.nom_complet if c.formateur else "sans formateur"
    return f"{c.id}  {c.titre}  [{f}]  {', '.join(map(str, c.creneaux))}"
def pct(x): return "n/a" if x is None else f"{x * 100:.0f} %"


def a_creer_etudiant(s: Systeme):
    id_ = s.ajouter_etudiant(lire_texte("Nom : "), lire_texte("Prenom : "),
                             lire_texte("Email : ", False), lire_texte("Filiere : ", False))
    print(f"OK Etudiant cree ({id_})")


def a_creer_formateur(s: Systeme):
    id_ = s.ajouter_formateur(lire_texte("Nom : "), lire_texte("Prenom : "),
                              lire_texte("Email : ", False), lire_texte("Specialite : ", False))
    print(f"OK Formateur cree ({id_})")


def a_lister_personnes(s: Systeme):
    print("Etudiants :")
    for e in s.etudiants.values():
        print("  ", l_etu(e))
    print("Formateurs :")
    for f in s.formateurs.values():
        print("  ", l_for(f))


def a_creer_cours(s: Systeme):
    titre = lire_texte("Titre : ")
    cap = lire_nombre("Capacite : ", 1, entier=True)
    creneaux = lire_creneaux()
    f = None
    if s.formateurs:
        f = choisir("Formateur", list(s.formateurs.values()), l_for)
    id_ = s.creer_cours(titre, cap, creneaux, f.id if f else None)
    print(f"OK Cours cree ({id_})")


def a_lister_cours(s: Systeme):
    for c in s.cours.values():
        _, nb, cap = s.taux_remplissage(c.id)
        print(f"  {l_cours(c)}  ({nb}/{cap}, attente : {len(c.en_attente())})")
    if not s.cours:
        print("  (aucun cours)")


def a_changer_formateur(s: Systeme):
    c = choisir("Cours", list(s.cours.values()), l_cours)
    if not c:
        return
    f = choisir("Nouveau formateur", list(s.formateurs.values()), l_for)
    if f:
        s.assigner_formateur(c.id, f.id)
        print("OK Formateur modifie")


def a_inscrire(s: Systeme):
    e = choisir("Etudiant", list(s.etudiants.values()), l_etu)
    if not e:
        return
    c = choisir("Cours", list(s.cours.values()), l_cours)
    if not c:
        return
    insc = s.inscrire(e.id, c.id)
    if insc.statut == CONFIRMEE:
        print("OK Inscription confirmee")
    else:
        rang = [i.id for i in s.cours[c.id].en_attente()].index(insc.id) + 1
        print(f" Cours complet : place en liste d'attente (rang {rang})")


def a_desister(s: Systeme):
    e = choisir("Etudiant", list(s.etudiants.values()), l_etu)
    if not e:
        return
    actives = [i for i in e.inscriptions if i.statut != "annulee"]
    i = choisir("Inscription a annuler", actives,
                lambda i: f"{i.cours.titre}  ({i.statut})")
    if not i:
        return
    promu = s.desister(i.id)
    print("OK Desistement enregistre")
    if promu:
        print(f"  -> place attribuee a {s.etudiants[promu].nom_complet} (liste d'attente)")


def a_file_attente(s: Systeme):
    c = choisir("Cours", list(s.cours.values()), l_cours)
    if c:
        for k, i in enumerate(c.en_attente(), 1):
            print(f"  {k}. {i.etudiant.nom_complet}")
        if not c.en_attente():
            print("  (file vide)")


def a_creer_eval(s: Systeme):
    c = choisir("Cours", list(s.cours.values()), l_cours)
    if not c:
        return
    id_ = s.creer_evaluation(c.id, lire_texte("Titre : "),
                             lire_nombre("Coefficient : ", 0.0001),
                             lire_nombre("Seuil de reussite (defaut 10) : ", 0, 20))
    print(f"OK Evaluation creee ({id_})")


def a_saisir_note(s: Systeme):
    ev = choisir("Evaluation", list(s.evaluations.values()),
                 lambda v: f"{v.id}  {v.titre}  ({s.cours[v.cours_id].titre}, coef {v.coefficient:g})")
    if not ev:
        return
    inscrits = [i.etudiant for i in s.cours[ev.cours_id].confirmees()]
    e = choisir("Etudiant", inscrits, l_etu)
    if e:
        s.saisir_note(ev.id, e.id, lire_nombre("Note /20 : ", 0, 20))
        print("OK Note enregistree")


def a_politique(s: Systeme):
    p = choisir(f"Note manquante (actuel : {s.politique_notes})", list(POLITIQUES_NOTES),
                lambda x: {"ignorer": "ignoree dans la moyenne", "zero": "comptee comme 0"}[x])
    if p:
        s.definir_politique_notes(p)
        print("OK Politique mise a jour")


def d_resultats(s: Systeme):
    e = choisir("Etudiant", list(s.etudiants.values()), l_etu)
    if not e:
        return
    res = s.resultats_etudiant(e.id)
    print(f"Resultats de {e.nom_complet} (note manquante : {s.politique_notes})")
    for r in res:
        m = "n/a" if r["moyenne"] is None else f"{r['moyenne']:.2f}/20"
        print(f"  {r['cours']} -> moyenne {m}")
        for titre, coef, note in r["notes"]:
            print(f"     - {titre} (coef {coef:g}) : {'-' if note is None else f'{note:g}'}")
    if not res:
        print("  (aucun cours confirme)")


def d_reussite(s: Systeme):
    print("Taux de reussite par evaluation :")
    for ev in s.evaluations.values():
        t, n = s.taux_reussite_evaluation(ev.id)
        print(f"  {s.cours[ev.cours_id].titre} / {ev.titre} : {pct(t)}  ({n} note(s), seuil {ev.seuil:g})")
    print("Taux de reussite par cours (moyenne >= 10) :")
    for c in s.cours.values():
        t, n = s.taux_reussite_cours(c.id)
        print(f"  {c.titre} : {pct(t)}  ({n} etudiant(s) note(s))")


def d_remplissage(s: Systeme):
    print("Taux de remplissage :")
    for c in s.cours.values():
        t, nb, cap = s.taux_remplissage(c.id)
        barre = "#" * round(t * 10) + "-" * (10 - round(t * 10))
        print(f"  {c.titre:<28} {barre} {pct(t)}  ({nb}/{cap}, attente : {len(c.en_attente())})")


def d_historique(s: Systeme):
    importants = [h for h in s.historique if h["action"] != "CREATION_COURS"]
    for h in importants[-30:]:
        print(f"  {h['date']}  {h['action']:<20} {h['details']}")
    if not importants:
        print("  (historique vide)")


def sous_menu(s: Systeme, titre: str, options: list):
    while True:
        print(f"\n- {titre} -")
        for k, (lib, _) in enumerate(options, 1):
            print(f" {k}. {lib}")
        print(" 0. Retour")
        n = lire_nombre("Choix : ", 0, len(options), entier=True)
        if n == 0:
            return
        try:
            options[n - 1][1](s)
        except ErreurMetier as e:
            print(f"Erreur {e}")


def boucle(s: Systeme):
    principal = [
        ("Personnes", [("Creer un etudiant", a_creer_etudiant), ("Creer un formateur", a_creer_formateur),
                       ("Lister", a_lister_personnes)]),
        ("Cours", [("Creer un cours", a_creer_cours), ("Lister les cours", a_lister_cours),
                   ("Changer le formateur d'un cours", a_changer_formateur)]),
        ("Inscriptions", [("Inscrire un etudiant", a_inscrire), ("Desistement", a_desister),
                          ("Voir la file d'attente", a_file_attente)]),
        ("Evaluations", [("Creer une evaluation", a_creer_eval), ("Saisir une note", a_saisir_note),
                         ("Regle des notes manquantes", a_politique)]),
        ("Tableaux de bord", [("Resultats d'un etudiant", d_resultats), ("Taux de reussite", d_reussite),
                              ("Taux de remplissage", d_remplissage)]),
        ("Historique des operations", [("Afficher l'historique", d_historique)]),
    ]
    while True:
        print("\n===== GESTION DE FORMATION =====")
        for k, (lib, _) in enumerate(principal, 1):
            print(f" {k}. {lib}")
        print(" 0. Quitter")
        n = lire_nombre("Choix : ", 0, len(principal), entier=True)
        if n == 0:
            print("Au revoir (donnees deja sauvegardees).")
            return
        sous_menu(s, principal[n - 1][0], principal[n - 1][1])


def main():
    chemin = Path(sys.argv[1]) if len(sys.argv) > 1 else CHEMIN_DEFAUT
    try:
        s = charger(chemin)
    except ErreurFichier as e:
        print(f"Erreur Impossible de demarrer : {e}")
        sys.exit(1)
    print(f"Donnees : {chemin}  ({len(s.etudiants)} etudiants, {len(s.formateurs)} formateurs, "
          f"{len(s.cours)} cours)")
    try:
        boucle(s)
    except (EOFError, KeyboardInterrupt):
        print("\nInterruption : aucune donnee perdue (sauvegarde apres chaque operation).")
    except OSError as e:
        print(f"Erreur Erreur d'ecriture : {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
