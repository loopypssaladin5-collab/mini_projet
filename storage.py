from __future__ import annotations

import json
import os
import re
from pathlib import Path

from models import (Cours, ErreurFichier, ErreurMetier, Evaluation, Inscription, Personne,
                    Etudiant, Formateur)
from service import POLITIQUES_NOTES, Systeme

VERSION = 1


def vers_dict(s: Systeme) -> dict:
    return {
        "version": VERSION,
        "compteurs": s.compteurs,
        "politique_notes": s.politique_notes,
        "personnes": [p.to_dict() for p in (*s.etudiants.values(), *s.formateurs.values())],
        "cours": [c.to_dict() for c in s.cours.values()],
        "inscriptions": [i.to_dict() for i in s.inscriptions.values()],
        "evaluations": [e.to_dict() for e in s.evaluations.values()],
        "historique": s.historique,
    }


def sauvegarder(s: Systeme, chemin: Path) -> None:
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_suffix(chemin.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(vers_dict(s), f, ensure_ascii=True, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, chemin)


def _recaler_compteurs(s: Systeme) -> None:
    groupes = {"E": s.etudiants, "F": s.formateurs, "C": s.cours,
               "I": s.inscriptions, "V": s.evaluations}
    for prefixe, dico in groupes.items():
        maxi = 0
        for id_ in dico:
            m = re.fullmatch(prefixe + r"(\d+)", id_)
            if m:
                maxi = max(maxi, int(m.group(1)))
        s.compteurs[prefixe] = max(s.compteurs.get(prefixe, 0), maxi)
    s.compteurs["ordre"] = max(s.compteurs.get("ordre", 0),
                               max((i.ordre for i in s.inscriptions.values()), default=0))


def depuis_dict(d: dict, persister=None) -> Systeme:
    s = Systeme(persister)
    try:
        if d.get("version") != VERSION:
            raise ErreurFichier(f"Version de fichier non supportee : {d.get('version')!r}")
        s.compteurs = {k: int(v) for k, v in d.get("compteurs", {}).items()}
        s.politique_notes = d.get("politique_notes", "ignorer")
        if s.politique_notes not in POLITIQUES_NOTES:
            raise ErreurFichier("Politique de notes invalide.")
        for pd in d["personnes"]:
            p = Personne.from_dict(pd)
            cible = s.etudiants if isinstance(p, Etudiant) else s.formateurs
            if p.id in s.etudiants or p.id in s.formateurs:
                raise ErreurFichier(f"Identifiant en double : {p.id}")
            cible[p.id] = p
        for ordre_cle, classe, dico in (("cours", Cours, s.cours),
                                        ("inscriptions", Inscription, s.inscriptions),
                                        ("evaluations", Evaluation, s.evaluations)):
            for x in d[ordre_cle]:
                obj = classe.from_dict(x)
                if obj.id in dico:
                    raise ErreurFichier(f"Identifiant en double : {obj.id}")
                dico[obj.id] = obj
        s.historique = list(d.get("historique", []))
        _recaler_compteurs(s)
        s.relier()
    except ErreurFichier:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, ErreurMetier) as e:
        raise ErreurFichier(f"Structure invalide ({type(e).__name__} : {e})")
    return s


def charger(chemin) -> Systeme:
    chemin = Path(chemin)
    persister = lambda s: sauvegarder(s, chemin)
    if not chemin.exists():
        s = Systeme(persister)
        persister(s)
        return s
    try:
        with open(chemin, encoding="utf-8") as f:
            d = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ErreurFichier(f"{chemin} n'est pas un JSON valide ({e}). Fichier laisse intact.")
    if not isinstance(d, dict):
        raise ErreurFichier(f"{chemin} : contenu inattendu. Fichier laisse intact.")
    return depuis_dict(d, persister)
