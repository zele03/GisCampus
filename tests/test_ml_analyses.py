"""Provere ML prostornih analiza bez pristupa projektnoj bazi."""

import unittest
from unittest.mock import patch

import geopandas as gpd
from shapely.geometry import box

from src.giscampus.geo import analysis


class TestMlAnalize(unittest.TestCase):
    def setUp(self):
        self.slojevi = {
            "zone": gpd.GeoDataFrame(
                {"naziv": ["Severna"]}, geometry=[box(0, 0, 10, 10)], crs=32634
            ),
            "ml_zgrade": gpd.GeoDataFrame(
                {
                    "ml_zgrada_id": [1, 2, 3],
                    "zona_id": [99, 1, 1],
                    "pouzdanost": [0.9, 0.8, 0.7],
                    "status_provere": ["potvrdjeno", "nije_potvrdjeno", "odbijeno"],
                },
                geometry=[box(1, 1, 3, 3), box(9, 1, 11, 3), box(20, 20, 22, 22)],
                crs=32634,
            ),
            "zgrade": gpd.GeoDataFrame(
                {"zgrada_id": [10, 11], "naziv": ["Zgrada A", "Zgrada B"]},
                geometry=[box(2, 1, 4, 3), box(3, 3, 4, 4)],
                crs=32634,
            ),
        }
        self.ucitavanje = patch.object(
            analysis, "ucitaj_sloj_za_analizu", side_effect=self.slojevi.__getitem__
        )
        self.ucitavanje.start()
        self.addCleanup(self.ucitavanje.stop)

    def test_within_koristi_geometriju_ne_strani_kljuc(self):
        rezultat = analysis.analiza_ml_zgrada_u_severnoj_zoni()
        self.assertEqual(rezultat.ml_zgrada_id.tolist(), [1])
        self.assertEqual(rezultat.povrsina_m2.tolist(), [4.0])
        self.assertTrue(
            rezultat.geometry.iloc[0].equals(
                self.slojevi["ml_zgrade"].geometry.iloc[0]
            )
        )

    def test_intersection_vraca_samo_zajednicku_povrsinu(self):
        rezultat = analysis.analiza_preseka_ml_i_evidentiranih_zgrada()
        self.assertEqual(rezultat.ml_zgrada_id.tolist(), [1])
        self.assertEqual(rezultat.zgrada_id.tolist(), [10])
        self.assertEqual(rezultat.povrsina_preseka_m2.tolist(), [2.0])
        self.assertEqual(self.slojevi["ml_zgrade"].geometry.area.tolist(), [4, 4, 4])

    def test_prazne_detekcije(self):
        self.slojevi["ml_zgrade"] = self.slojevi["ml_zgrade"].iloc[:0].copy()
        self.assertTrue(analysis.analiza_ml_zgrada_u_severnoj_zoni().empty)
        self.assertTrue(analysis.analiza_preseka_ml_i_evidentiranih_zgrada().empty)

    def test_nedostaje_severna_zona(self):
        self.slojevi["zone"] = self.slojevi["zone"].iloc[:0].copy()
        with self.assertRaises(RuntimeError):
            analysis.analiza_ml_zgrada_u_severnoj_zoni()


if __name__ == "__main__":
    unittest.main()
