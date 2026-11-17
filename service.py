from __future__ import annotations

import copy
import functools
from datetime import datetime

from models import (ANNULEE, CONFIRMEE, EN_ATTENTE, Cours, Creneau, ErreurFichier,
                    ErreurMetier, Etudiant, Evaluation, Formateur, Inscription)

POLITIQUES_NOTES = ("ignorer", "zero")


def transaction(f):
    @functools.wraps(f)
    def wrapper(self, *args, **kwargs):
        persister, self.persister = self.persister, None
        snapshot = copy.deepcopy(self.__dict__)
        self.persister = persister
        try:
            resultat = f(self, *args, **kwargs)
            self.relier()
            if self.persister:
                self.persister(self)
            return resultat
        except Exception:
            self.__dict__.clear()
            self.__dict__.update(snapshot)
            self.persister = persister
            raise
    return wrapper


class Systeme:
    def __init__(self, persister=None):
        self.etudiants: dict[str, Etudiant] = {}
        self.formateurs: dict[str, Formateur] = {}
        self.cours: dict[str, Cours] = {}
        self.inscriptions: dict[str, Inscription] = {}
        self.evaluations: dict[str, Evaluation] = {}
        self.historique: list[dict] = []
        self.compteurs: dict[str, int] = {}
        self.politique_notes = "ignorer"
        self.persister = persister

    def _nouvel_id(self, prefixe: str) -> str:
        self.compteurs[prefixe] = self.compteurs.get(prefixe, 0) + 1
        return f"{prefixe}{self.compteurs[prefixe]:03d}"

    def _log(self, action: str, details: str) -> None:
        self.historique.append({"date": datetime.now().isoformat(timespec="seconds"),
                                "action": action, "details": details})

    @staticmethod
    def _get(dico: dict, id: str, nom: str):
        if id not in dico:
            raise ErreurMetier(f"{nom} introuvable : {id}")
        return dico[id]

    def relier(self) -> None:
        for e in self.etudiants.values():
            e.inscriptions = []
        for f in self.formateurs.values():
            f.cours = []
        for c in self.cours.values():
            c.inscriptions = []
            c.formateur = None
            if c.formateur_id is not None:
                f = self.formateurs.get(c.formateur_id)
                if f is None:
                    raise ErreurFichier(f"Cours {c.id} : formateur {c.formateur_id} inconnu")
                c.formateur = f
                f.cours.append(c)
        for i in self.inscriptions.values():
            e, c = self.etudiants.get(i.etudiant_id), self.cours.get(i.cours_id)
            if e is None or c is None:
                raise ErreurFichier(f"Inscription {i.id} : etudiant ou cours inconnu")
            i.etudiant, i.cours = e, c
            e.inscriptions.append(i)
            c.inscriptions.append(i)
        for ev in self.evaluations.values():
            if ev.cours_id not in self.cours:
                raise ErreurFichier(f"Evaluation {ev.id} : cours {ev.cours_id} inconnu")
            for etu_id in ev.notes:
                if etu_id not in self.etudiants:
                    raise ErreurFichier(f"Evaluation {ev.id} : etudiant {etu_id} inconnu")

    @staticmethod
    def _conflit(creneaux: list[Creneau], autres_cours, ignorer: str | None = None):
        for c in autres_cours:
            if c.id == ignorer:
                continue
            for a in creneaux:
                for b in c.creneaux:
                    if a.chevauche(b):
                        return c, b
        return None

    def _cours_etudiant(self, etu_id: str, statuts=(CONFIRMEE, EN_ATTENTE)) -> list[Cours]:
        return [self.cours[i.cours_id] for i in self.inscriptions.values()
                if i.etudiant_id == etu_id and i.statut in statuts]

    def _cours_formateur(self, formateur_id: str) -> list[Cours]:
        return [c for c in self.cours.values() if c.formateur_id == formateur_id]

    @transaction
    def ajouter_etudiant(self, nom, prenom, email="", filiere="") -> str:
        nom, prenom = nom.strip(), prenom.strip()
        if not nom or not prenom:
            raise ErreurMetier("Nom et prenom obligatoires.")
        e = Etudiant(self._nouvel_id("E"), nom, prenom, email.strip(), filiere.strip())
        self.etudiants[e.id] = e
        return e.id

    @transaction
    def ajouter_formateur(self, nom, prenom, email="", specialite="") -> str:
        nom, prenom = nom.strip(), prenom.strip()
        if not nom or not prenom:
            raise ErreurMetier("Nom et prenom obligatoires.")
        f = Formateur(self._nouvel_id("F"), nom, prenom, email.strip(), specialite.strip())
        self.formateurs[f.id] = f
        return f.id

    @transaction
    def creer_cours(self, titre, capacite, creneaux, formateur_id=None) -> str:
        if not titre.strip():
            raise ErreurMetier("Titre obligatoire.")
        if capacite < 1:
            raise ErreurMetier("La capacite doit etre d'au moins 1.")
        if not creneaux:
            raise ErreurMetier("Au moins un creneau est requis.")
        if formateur_id is not None:
            self._get(self.formateurs, formateur_id, "Formateur")
            conflit = self._conflit(creneaux, self._cours_formateur(formateur_id))
            if conflit:
                raise ErreurMetier(f"Le formateur est deja pris : '{conflit[0].titre}' ({conflit[1]}).")
        c = Cours(self._nouvel_id("C"), titre.strip(), capacite, list(creneaux), formateur_id)
        self.cours[c.id] = c
        self._log("CREATION_COURS", f"{c.id}'{c.titre}' (capacite {capacite})")
        return c.id

    @transaction
    def assigner_formateur(self, cours_id: str, formateur_id: str) -> None:
        c = self._get(self.cours, cours_id, "Cours")
        f = self._get(self.formateurs, formateur_id, "Formateur")
        if c.formateur_id == formateur_id:
            raise ErreurMetier("Ce formateur est deja assigne a ce cours.")
        conflit = self._conflit(c.creneaux, self._cours_formateur(formateur_id), ignorer=c.id)
        if conflit:
            raise ErreurMetier(f"{f.nom_complet} a deja '{conflit[0].titre}' ({conflit[1]}).")
        ancien = c.formateur_id or "aucun"
        c.formateur_id = formateur_id
        self._log("CHANGEMENT_FORMATEUR", f"{c.id}'{c.titre}' : {ancien} -> {formateur_id}")

    @transaction
    def inscrire(self, etudiant_id: str, cours_id: str) -> Inscription:
        etu = self._get(self.etudiants, etudiant_id, "Etudiant")
        cours = self._get(self.cours, cours_id, "Cours")
        if any(i.etudiant_id == etudiant_id and i.cours_id == cours_id and i.statut != ANNULEE
               for i in self.inscriptions.values()):
            raise ErreurMetier("Cet etudiant est deja inscrit (ou en attente) a ce cours.")
        conflit = self._conflit(cours.creneaux, self._cours_etudiant(etudiant_id))
        if conflit:
            raise ErreurMetier(f"Conflit d'horaires avec '{conflit[0].titre}' ({conflit[1]}).")
        confirmees = [i for i in self.inscriptions.values()
                      if i.cours_id == cours_id and i.statut == CONFIRMEE]
        attente = [i for i in self.inscriptions.values()
                   if i.cours_id == cours_id and i.statut == EN_ATTENTE]
        statut = CONFIRMEE if len(confirmees) < cours.capacite and not attente else EN_ATTENTE
        self.compteurs["ordre"] = self.compteurs.get("ordre", 0) + 1
        insc = Inscription(self._nouvel_id("I"), etudiant_id, cours_id, statut, self.compteurs["ordre"])
        self.inscriptions[insc.id] = insc
        self._log("INSCRIPTION", f"{etu.nom_complet} -> '{cours.titre}' ({statut})")
        return insc

    @transaction
    def desister(self, inscription_id: str) -> str | None:
        insc = self._get(self.inscriptions, inscription_id, "Inscription")
        if insc.statut == ANNULEE:
            raise ErreurMetier("Cette inscription est deja annulee.")
        etu, cours = self.etudiants[insc.etudiant_id], self.cours[insc.cours_id]
        etait_confirmee = insc.statut == CONFIRMEE
        insc.statut = ANNULEE
        self._log("DESISTEMENT", f"{etu.nom_complet} quitte '{cours.titre}'")
        return self._promouvoir(cours.id) if etait_confirmee else None

    def _promouvoir(self, cours_id: str) -> str | None:
        cours = self.cours[cours_id]
        nb = sum(1 for i in self.inscriptions.values()
                 if i.cours_id == cours_id and i.statut == CONFIRMEE)
        if nb >= cours.capacite:
            return None
        file = sorted((i for i in self.inscriptions.values()
                       if i.cours_id == cours_id and i.statut == EN_ATTENTE), key=lambda i: i.ordre)
        for cand in file:
            deja = self._cours_etudiant(cand.etudiant_id, (CONFIRMEE,))
            if not self._conflit(cours.creneaux, deja):
                cand.statut = CONFIRMEE
                etu = self.etudiants[cand.etudiant_id]
                self._log("PROMOTION", f"{etu.nom_complet} passe de la file d'attente a '{cours.titre}'")
                return etu.id
        return None

    @transaction
    def definir_politique_notes(self, politique: str) -> None:
        if politique not in POLITIQUES_NOTES:
            raise ErreurMetier(f"Politique inconnue (choix : {', '.join(POLITIQUES_NOTES)}).")
        self.politique_notes = politique
        self._log("POLITIQUE_NOTES", f"note manquante : {politique}")

    @transaction
    def creer_evaluation(self, cours_id, titre, coefficient, seuil=10.0) -> str:
        self._get(self.cours, cours_id, "Cours")
        if not titre.strip():
            raise ErreurMetier("Titre obligatoire.")
        if coefficient <= 0:
            raise ErreurMetier("Le coefficient doit etre strictement positif.")
        if not 0 <= seuil <= 20:
            raise ErreurMetier("Le seuil doit etre entre 0 et 20.")
        ev = Evaluation(self._nouvel_id("V"), cours_id, titre.strip(), float(coefficient), float(seuil))
        self.evaluations[ev.id] = ev
        return ev.id

    @transaction
    def saisir_note(self, evaluation_id: str, etudiant_id: str, note: float) -> None:
        ev = self._get(self.evaluations, evaluation_id, "Evaluation")
        self._get(self.etudiants, etudiant_id, "Etudiant")
        if not 0 <= note <= 20:
            raise ErreurMetier("La note doit etre comprise entre 0 et 20.")
        if not any(i.etudiant_id == etudiant_id and i.cours_id == ev.cours_id and i.statut == CONFIRMEE
                   for i in self.inscriptions.values()):
            raise ErreurMetier("Cet etudiant n'est pas inscrit (confirme) a ce cours.")
        ev.notes[etudiant_id] = float(note)

    def moyenne(self, etudiant_id: str, cours_id: str) -> float | None:
        num = den = 0.0
        for ev in self.evaluations.values():
            if ev.cours_id != cours_id:
                continue
            note = ev.notes.get(etudiant_id)
            if note is None:
                if self.politique_notes == "zero":
                    note = 0.0
                else:
                    continue
            num += note * ev.coefficient
            den += ev.coefficient
        return num / den if den else None

    def resultats_etudiant(self, etudiant_id: str) -> list[dict]:
        self._get(self.etudiants, etudiant_id, "Etudiant")
        res = []
        for i in self.inscriptions.values():
            if i.etudiant_id != etudiant_id or i.statut != CONFIRMEE:
                continue
            notes = [(ev.titre, ev.coefficient, ev.notes.get(etudiant_id))
                     for ev in self.evaluations.values() if ev.cours_id == i.cours_id]
            res.append({"cours": self.cours[i.cours_id].titre, "notes": notes,
                        "moyenne": self.moyenne(etudiant_id, i.cours_id)})
        return res

    def taux_reussite_evaluation(self, evaluation_id: str) -> tuple[float | None, int]:
        ev = self._get(self.evaluations, evaluation_id, "Evaluation")
        notes = list(ev.notes.values())
        if not notes:
            return None, 0
        return sum(1 for n in notes if n >= ev.seuil) / len(notes), len(notes)

    def taux_reussite_cours(self, cours_id: str) -> tuple[float | None, int]:
        self._get(self.cours, cours_id, "Cours")
        moys = [self.moyenne(i.etudiant_id, cours_id) for i in self.inscriptions.values()
                if i.cours_id == cours_id and i.statut == CONFIRMEE]
        moys = [m for m in moys if m is not None]
        if not moys:
            return None, 0
        return sum(1 for m in moys if m >= 10) / len(moys), len(moys)

    def taux_remplissage(self, cours_id: str) -> tuple[float, int, int]:
        c = self._get(self.cours, cours_id, "Cours")
        nb = sum(1 for i in self.inscriptions.values()
                 if i.cours_id == cours_id and i.statut == CONFIRMEE)
        return nb / c.capacite, nb, c.capacite
