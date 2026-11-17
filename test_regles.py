import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models import ANNULEE, CONFIRMEE, EN_ATTENTE, Creneau as C, ErreurFichier, ErreurMetier
from storage import charger


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.chemin = Path(self.dir.name) / "d.json"
        self.s = charger(self.chemin)

    def tearDown(self):
        self.dir.cleanup()


class TestRegles(Base):
    def test_conflit_etudiant(self):
        s = self.s
        f = s.ajouter_formateur("A", "B")
        g = s.ajouter_formateur("C", "D")
        c1 = s.creer_cours("X", 5, [C("lundi", "08:00", "10:00")], f)
        c2 = s.creer_cours("Y", 5, [C("lundi", "09:00", "11:00")], g)
        e = s.ajouter_etudiant("N", "P")
        s.inscrire(e, c1)
        with self.assertRaises(ErreurMetier):
            s.inscrire(e, c2)
        self.assertEqual(len(s.inscriptions), 1)

    def test_creneaux_adjacents_ok(self):
        s = self.s
        c1 = s.creer_cours("X", 5, [C("lundi", "08:00", "10:00")])
        c2 = s.creer_cours("Y", 5, [C("lundi", "10:00", "12:00")])
        e = s.ajouter_etudiant("N", "P")
        s.inscrire(e, c1)
        s.inscrire(e, c2)

    def test_conflit_formateur(self):
        s = self.s
        f = s.ajouter_formateur("A", "B")
        s.creer_cours("X", 5, [C("lundi", "08:00", "10:00")], f)
        with self.assertRaises(ErreurMetier):
            s.creer_cours("Y", 5, [C("lundi", "09:00", "10:30")], f)
        c3 = s.creer_cours("Z", 5, [C("lundi", "09:00", "10:30")])
        with self.assertRaises(ErreurMetier):
            s.assigner_formateur(c3, f)
        self.assertIsNone(s.cours[c3].formateur_id)

    def test_capacite_et_promotion(self):
        s = self.s
        c = s.creer_cours("X", 1, [C("mardi", "08:00", "10:00")])
        a, b, d = (s.ajouter_etudiant(n, "P") for n in "ABD")
        ia = s.inscrire(a, c)
        ib = s.inscrire(b, c)
        id_ = s.inscrire(d, c)
        self.assertEqual([ia.statut, ib.statut, id_.statut], [CONFIRMEE, EN_ATTENTE, EN_ATTENTE])
        promu = s.desister(ia.id)
        self.assertEqual(promu, b)
        self.assertEqual(s.inscriptions[ib.id].statut, CONFIRMEE)
        self.assertEqual(s.inscriptions[id_.id].statut, EN_ATTENTE)
        self.assertEqual(s.inscriptions[ia.id].statut, ANNULEE)

    def test_promotion_saute_candidat_en_conflit(self):
        s = self.s
        c1 = s.creer_cours("X", 1, [C("mardi", "08:00", "10:00")])
        c2 = s.creer_cours("Y", 5, [C("mardi", "09:00", "11:00")])
        a, b, d = (s.ajouter_etudiant(n, "P") for n in "ABD")
        i1 = s.inscrire(a, c1)
        ib = s.inscrire(b, c1)
        s.inscrire(d, c1)
        s.inscriptions[ib.id].statut = ANNULEE
        s.inscrire(b, c2)
        s.inscriptions[ib.id].statut = EN_ATTENTE
        s.relier()
        promu = s.desister(i1.id)
        self.assertEqual(promu, d)

    def test_pas_de_doublon_inscription(self):
        s = self.s
        c = s.creer_cours("X", 5, [C("mardi", "08:00", "10:00")])
        e = s.ajouter_etudiant("N", "P")
        s.inscrire(e, c)
        with self.assertRaises(ErreurMetier):
            s.inscrire(e, c)

    def test_moyenne_ponderee_et_notes_manquantes(self):
        s = self.s
        c = s.creer_cours("X", 5, [C("mardi", "08:00", "10:00")])
        e = s.ajouter_etudiant("N", "P")
        s.inscrire(e, c)
        v1 = s.creer_evaluation(c, "TP", 1)
        v2 = s.creer_evaluation(c, "Exam", 3)
        s.saisir_note(v1, e, 10)
        self.assertAlmostEqual(s.moyenne(e, c), 10)
        s.definir_politique_notes("zero")
        self.assertAlmostEqual(s.moyenne(e, c), 10 / 4)
        s.saisir_note(v2, e, 14)
        self.assertAlmostEqual(s.moyenne(e, c), (10 + 42) / 4)

    def test_note_invalide_ou_non_inscrit(self):
        s = self.s
        c = s.creer_cours("X", 5, [C("mardi", "08:00", "10:00")])
        e = s.ajouter_etudiant("N", "P")
        v = s.creer_evaluation(c, "TP", 1)
        with self.assertRaises(ErreurMetier):
            s.saisir_note(v, e, 12)
        s.inscrire(e, c)
        with self.assertRaises(ErreurMetier):
            s.saisir_note(v, e, 25)

    def test_stats(self):
        s = self.s
        c = s.creer_cours("X", 4, [C("mardi", "08:00", "10:00")])
        a, b = s.ajouter_etudiant("A", "P"), s.ajouter_etudiant("B", "P")
        s.inscrire(a, c)
        s.inscrire(b, c)
        v = s.creer_evaluation(c, "TP", 1)
        s.saisir_note(v, a, 15)
        s.saisir_note(v, b, 5)
        self.assertEqual(s.taux_reussite_evaluation(v), (0.5, 2))
        self.assertEqual(s.taux_remplissage(c), (0.5, 2, 4))


class TestPersistance(Base):
    def test_fichier_cree_si_absent(self):
        self.assertTrue(self.chemin.exists())

    def test_aller_retour_et_liens(self):
        s = self.s
        f = s.ajouter_formateur("Martin", "Claire")
        e = s.ajouter_etudiant("Petit", "Hugo")
        c = s.creer_cours("X", 2, [C("lundi", "08:00", "10:00")], f)
        s.inscrire(e, c)
        s2 = charger(self.chemin)
        c2 = s2.cours[c]
        self.assertEqual(c2.formateur.nom, "Martin")
        self.assertEqual([i.etudiant.nom for i in c2.confirmees()], ["Petit"])
        self.assertEqual(type(s2.etudiants[e]).__name__, "Etudiant")
        self.assertEqual(type(s2.formateurs[f]).__name__, "Formateur")

    def test_ids_uniques_apres_redemarrage(self):
        s = self.s
        a = s.ajouter_etudiant("A", "P")
        s2 = charger(self.chemin)
        b = s2.ajouter_etudiant("B", "P")
        self.assertNotEqual(a, b)
        d = json.loads(self.chemin.read_text())
        d["compteurs"] = {}
        self.chemin.write_text(json.dumps(d))
        s3 = charger(self.chemin)
        self.assertNotIn(s3.ajouter_etudiant("C", "P"), (a, b))

    def test_fichier_invalide_non_ecrase(self):
        self.chemin.write_text("{ pas du json")
        with self.assertRaises(ErreurFichier):
            charger(self.chemin)
        self.assertEqual(self.chemin.read_text(), "{ pas du json")

    def test_structure_incoherente_non_ecrasee(self):
        contenu = json.dumps({"version": 1, "personnes": [], "cours": [{"id": "C001"}],
                              "inscriptions": [], "evaluations": []})
        self.chemin.write_text(contenu)
        with self.assertRaises(ErreurFichier):
            charger(self.chemin)
        self.assertEqual(self.chemin.read_text(), contenu)

    def test_rollback_si_sauvegarde_echoue(self):
        s = self.s
        s.persister = lambda _s: (_ for _ in ()).throw(OSError("disque plein"))
        with self.assertRaises(OSError):
            s.ajouter_etudiant("A", "P")
        self.assertEqual(len(s.etudiants), 0)


if __name__ == "__main__":
    unittest.main()
