from __future__ import annotations

from dataclasses import dataclass

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]

CONFIRMEE = "confirmee"
EN_ATTENTE = "en_attente"
ANNULEE = "annulee"
STATUTS = (CONFIRMEE, EN_ATTENTE, ANNULEE)


class ErreurMetier(Exception):
    pass


class ErreurFichier(Exception):
    pass


def _minutes(hhmm: str) -> int:
    try:
        h, m = hhmm.split(":")
        h, m = int(h), int(m)
    except ValueError:
        raise ErreurMetier(f"Heure invalide : {hhmm!r} (format HH:MM)")
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ErreurMetier(f"Heure invalide : {hhmm!r}")
    return h * 60 + m


@dataclass(frozen=True)
class Creneau:
    jour: str
    debut: str
    fin: str

    def __post_init__(self):
        if self.jour not in JOURS:
            raise ErreurMetier(f"Jour invalide : {self.jour!r}")
        if _minutes(self.debut) >= _minutes(self.fin):
            raise ErreurMetier("L'heure de debut doit preceder l'heure de fin.")

    def chevauche(self, autre: "Creneau") -> bool:
        return (
            self.jour == autre.jour
            and _minutes(self.debut) < _minutes(autre.fin)
            and _minutes(autre.debut) < _minutes(self.fin)
        )

    @staticmethod
    def parse(texte: str) -> "Creneau":
        try:
            jour, plage = texte.strip().lower().split()
            debut, fin = plage.split("-")
        except ValueError:
            raise ErreurMetier("Format attendu : jour HH:MM-HH:MM (ex : lundi 08:00-10:00)")
        return Creneau(jour, debut, fin)

    def to_dict(self) -> dict:
        return {"jour": self.jour, "debut": self.debut, "fin": self.fin}

    @staticmethod
    def from_dict(d: dict) -> "Creneau":
        return Creneau(d["jour"], d["debut"], d["fin"])

    def __str__(self) -> str:
        return f"{self.jour} {self.debut}-{self.fin}"


class Personne:
    type_nom = "personne"

    def __init__(self, id: str, nom: str, prenom: str, email: str = ""):
        self.id = id
        self.nom = nom
        self.prenom = prenom
        self.email = email

    @property
    def nom_complet(self) -> str:
        return f"{self.prenom} {self.nom}"

    def to_dict(self) -> dict:
        return {"type": self.type_nom, "id": self.id, "nom": self.nom,
                "prenom": self.prenom, "email": self.email}

    @staticmethod
    def from_dict(d: dict) -> "Personne":
        classes = {Etudiant.type_nom: Etudiant, Formateur.type_nom: Formateur}
        cls = classes.get(d.get("type"))
        if cls is None:
            raise ErreurFichier(f"Type de personne inconnu : {d.get('type')!r}")
        return cls._depuis(d)


class Etudiant(Personne):
    type_nom = "etudiant"

    def __init__(self, id, nom, prenom, email="", filiere=""):
        super().__init__(id, nom, prenom, email)
        self.filiere = filiere
        self.inscriptions: list[Inscription] = []

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["filiere"] = self.filiere
        return d

    @classmethod
    def _depuis(cls, d):
        return cls(d["id"], d["nom"], d["prenom"], d.get("email", ""), d.get("filiere", ""))


class Formateur(Personne):
    type_nom = "formateur"

    def __init__(self, id, nom, prenom, email="", specialite=""):
        super().__init__(id, nom, prenom, email)
        self.specialite = specialite
        self.cours: list[Cours] = []

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["specialite"] = self.specialite
        return d

    @classmethod
    def _depuis(cls, d):
        return cls(d["id"], d["nom"], d["prenom"], d.get("email", ""), d.get("specialite", ""))


class Cours:
    def __init__(self, id: str, titre: str, capacite: int,
                 creneaux: list[Creneau], formateur_id: str | None = None):
        self.id = id
        self.titre = titre
        self.capacite = capacite
        self.creneaux = creneaux
        self.formateur_id = formateur_id
        self.formateur: Formateur | None = None
        self.inscriptions: list[Inscription] = []

    def confirmees(self) -> list["Inscription"]:
        return [i for i in self.inscriptions if i.statut == CONFIRMEE]

    def en_attente(self) -> list["Inscription"]:
        return sorted((i for i in self.inscriptions if i.statut == EN_ATTENTE),
                      key=lambda i: i.ordre)

    @property
    def taux_remplissage(self) -> float:
        return len(self.confirmees()) / self.capacite if self.capacite else 0.0

    def to_dict(self) -> dict:
        return {"id": self.id, "titre": self.titre, "capacite": self.capacite,
                "formateur_id": self.formateur_id,
                "creneaux": [c.to_dict() for c in self.creneaux]}

    @staticmethod
    def from_dict(d: dict) -> "Cours":
        return Cours(d["id"], d["titre"], int(d["capacite"]),
                     [Creneau.from_dict(c) for c in d["creneaux"]], d.get("formateur_id"))


class Inscription:
    def __init__(self, id: str, etudiant_id: str, cours_id: str, statut: str, ordre: int):
        self.id = id
        self.etudiant_id = etudiant_id
        self.cours_id = cours_id
        self.statut = statut
        self.ordre = ordre
        self.etudiant: Etudiant | None = None
        self.cours: Cours | None = None

    def to_dict(self) -> dict:
        return {"id": self.id, "etudiant_id": self.etudiant_id, "cours_id": self.cours_id,
                "statut": self.statut, "ordre": self.ordre}

    @staticmethod
    def from_dict(d: dict) -> "Inscription":
        if d["statut"] not in STATUTS:
            raise ErreurFichier(f"Statut d'inscription inconnu : {d['statut']!r}")
        return Inscription(d["id"], d["etudiant_id"], d["cours_id"], d["statut"], int(d["ordre"]))


class Evaluation:
    def __init__(self, id: str, cours_id: str, titre: str, coefficient: float,
                 seuil: float = 10.0, notes: dict[str, float] | None = None):
        self.id = id
        self.cours_id = cours_id
        self.titre = titre
        self.coefficient = coefficient
        self.seuil = seuil
        self.notes = notes or {}

    def to_dict(self) -> dict:
        return {"id": self.id, "cours_id": self.cours_id, "titre": self.titre,
                "coefficient": self.coefficient, "seuil": self.seuil, "notes": self.notes}

    @staticmethod
    def from_dict(d: dict) -> "Evaluation":
        return Evaluation(d["id"], d["cours_id"], d["titre"], float(d["coefficient"]),
                          float(d.get("seuil", 10.0)),
                          {k: float(v) for k, v in d.get("notes", {}).items()})
