"""CRUD operacije nad projektnim SQL tabelama."""

from contextlib import closing
from typing import Any

import pandas as pd
from psycopg2 import Binary, sql
from shapely.geometry.base import BaseGeometry

from .database import povezi_se, ucitaj_tabele_u_dataframe

KONFIGURACIJA_TABELA = {
    "zone_kampusa": {
        "primarni_kljuc": "zona_id",
        "kolone": {"naziv", "oznaka", "povrsina_m2", "geometrija"},
    },
    "zgrade": {
        "primarni_kljuc": "zgrada_id",
        "kolone": {"zona_id", "naziv", "tip", "povrsina_m2", "geometrija"},
    },
    "parkiralista": {
        "primarni_kljuc": "parkiraliste_id",
        "kolone": {"zona_id", "naziv", "tip", "povrsina_m2", "geometrija"},
    },
    "zelene_povrsine": {
        "primarni_kljuc": "zelena_povrsina_id",
        "kolone": {"zona_id", "tip", "povrsina_m2", "geometrija"},
    },
    "infrastrukturni_objekti": {
        "primarni_kljuc": "infrastrukturni_objekat_id",
        "kolone": {"zona_id", "naziv", "stanje", "geometrija"},
    },
    "tereni": {
        "primarni_kljuc": "teren_id",
        "kolone": {"zona_id", "naziv", "povrsina_m2", "geometrija"},
    },
    "ml_zgrade": {
        "primarni_kljuc": "ml_zgrada_id",
        "kolone": {"status_provere"},
    },
}


def _proveri_tabelu(naziv_tabele: str) -> dict[str, Any]:
    """Proveri naziv tabele i vrati njenu CRUD konfiguraciju."""

    if naziv_tabele not in KONFIGURACIJA_TABELA:
        raise ValueError(f"CRUD nije dozvoljen za tabelu '{naziv_tabele}'.")

    return KONFIGURACIJA_TABELA[naziv_tabele]


def _proveri_kolone(naziv_tabele: str, podaci: dict[str, Any]) -> None:
    """Proveri da li su prosledjene kolone dozvoljene za izabranu tabelu."""

    konfiguracija = _proveri_tabelu(naziv_tabele)
    nedozvoljene_kolone = set(podaci) - konfiguracija["kolone"]

    if nedozvoljene_kolone:
        raise ValueError(
            f"Nedozvoljene kolone za tabelu '{naziv_tabele}': "
            + ", ".join(sorted(nedozvoljene_kolone))
        )


def prikazi_sve(naziv_tabele: str) -> pd.DataFrame:
    """Procitaj i vrati sve redove iz izabrane tabele kao DataFrame."""

    _proveri_tabelu(naziv_tabele)
    return ucitaj_tabele_u_dataframe()[naziv_tabele]


def dodaj_red(naziv_tabele: str, podaci: dict[str, Any]) -> int:
    """Dodaj novi red i vrati automatski dodeljen primarni kljuc."""

    if not podaci:
        raise ValueError("Za unos novog reda moraju se proslediti podaci.")

    konfiguracija = _proveri_tabelu(naziv_tabele)
    _proveri_kolone(naziv_tabele, podaci)
    kolone = tuple(podaci)

    upit = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING {};").format(
        sql.Identifier(naziv_tabele),
        sql.SQL(", ").join(map(sql.Identifier, kolone)),
        sql.SQL(", ").join(sql.Placeholder() for _ in kolone),
        sql.Identifier(konfiguracija["primarni_kljuc"]),
    )

    with closing(povezi_se()) as konekcija:
        with konekcija.cursor() as kursor:
            kursor.execute(upit, tuple(podaci[kolona] for kolona in kolone))
            novi_id = kursor.fetchone()[0]

        konekcija.commit()

    return novi_id


def dodaj_prostorni_red(
    naziv_tabele: str,
    podaci: dict[str, Any],
    geometrija: BaseGeometry,
) -> int:
    """Dodaj red sa obaveznom geometrijom i automatski izracunatom povrsinom."""

    konfiguracija = _proveri_tabelu(naziv_tabele)
    _proveri_kolone(naziv_tabele, podaci)
    automatske_kolone = {"povrsina_m2", "geometrija"}
    if naziv_tabele != "zone_kampusa":
        automatske_kolone.add("zona_id")
    obavezne_kolone = konfiguracija["kolone"] - automatske_kolone
    if set(podaci) != obavezne_kolone:
        raise ValueError(
            "Moraju biti prosledjene sve obavezne kolone: "
            + ", ".join(sorted(obavezne_kolone))
        )
    if any(
        vrednost is None or (isinstance(vrednost, str) and not vrednost.strip())
        for vrednost in podaci.values()
    ):
        raise ValueError("Sve atributske kolone moraju biti popunjene.")
    if geometrija is None or geometrija.is_empty or not geometrija.is_valid:
        raise ValueError("Geometrija mora biti nacrtana i ispravna.")

    ocekivani_tip = "Point" if naziv_tabele == "infrastrukturni_objekti" else "Polygon"
    if geometrija.geom_type != ocekivani_tip:
        raise ValueError(
            f"Za tabelu '{naziv_tabele}' potrebna je geometrija {ocekivani_tip}."
        )

    vrednosti = dict(podaci)
    if naziv_tabele != "zone_kampusa":
        zona_id, _ = pronadji_zonu_za_geometriju(geometrija)
        vrednosti["zona_id"] = zona_id
    if "povrsina_m2" in konfiguracija["kolone"]:
        vrednosti["povrsina_m2"] = round(geometrija.area, 2)

    kolone = tuple(vrednosti)
    geometrijski_izraz = (
        sql.SQL("ST_Multi(ST_GeomFromWKB(%s, 32634))")
        if naziv_tabele == "zgrade"
        else sql.SQL("ST_GeomFromWKB(%s, 32634)")
    )
    upit = sql.SQL(
        "INSERT INTO {} ({}, geometrija) VALUES ({}, {}) RETURNING {};"
    ).format(
        sql.Identifier(naziv_tabele),
        sql.SQL(", ").join(map(sql.Identifier, kolone)),
        sql.SQL(", ").join(sql.Placeholder() for _ in kolone),
        geometrijski_izraz,
        sql.Identifier(konfiguracija["primarni_kljuc"]),
    )

    with closing(povezi_se()) as konekcija:
        with konekcija.cursor() as kursor:
            kursor.execute(
                upit,
                (
                    *tuple(vrednosti[kolona] for kolona in kolone),
                    Binary(geometrija.wkb),
                ),
            )
            novi_id = kursor.fetchone()[0]
        konekcija.commit()

    return novi_id


def pronadji_zonu_za_geometriju(geometrija: BaseGeometry) -> tuple[int, str]:
    """Pronadji jedinu zonu koja potpuno sadrzi prosledjenu geometriju."""

    if geometrija is None or geometrija.is_empty or not geometrija.is_valid:
        raise ValueError("Geometrija mora biti nacrtana i ispravna.")

    with closing(povezi_se()) as konekcija, konekcija.cursor() as kursor:
        kursor.execute(
            """
            SELECT zona_id, naziv
            FROM zone_kampusa
            WHERE geometrija IS NOT NULL
              AND ST_Covers(geometrija, ST_GeomFromWKB(%s, 32634))
            ORDER BY zona_id;
            """,
            (Binary(geometrija.wkb),),
        )
        zone = kursor.fetchall()

    if not zone:
        raise ValueError("Nacrtana geometrija mora biti potpuno unutar jedne zone.")
    if len(zone) > 1:
        raise ValueError("Geometrija ne sme istovremeno pripadati razlicitim zonama.")

    return zone[0]


def azuriraj_red(
    naziv_tabele: str,
    vrednost_primarnog_kljuca: int,
    izmene: dict[str, Any],
) -> bool:
    """Azuriraj izabrani red i vrati da li je red pronadjen."""

    if not izmene:
        raise ValueError("Za azuriranje mora se proslediti najmanje jedna izmena.")

    konfiguracija = _proveri_tabelu(naziv_tabele)
    _proveri_kolone(naziv_tabele, izmene)
    kolone = tuple(izmene)
    dodele = sql.SQL(", ").join(
        sql.SQL("{} = {}").format(sql.Identifier(kolona), sql.Placeholder())
        for kolona in kolone
    )
    upit = sql.SQL("UPDATE {} SET {} WHERE {} = %s;").format(
        sql.Identifier(naziv_tabele),
        dodele,
        sql.Identifier(konfiguracija["primarni_kljuc"]),
    )
    vrednosti = tuple(izmene[kolona] for kolona in kolone)

    with closing(povezi_se()) as konekcija:
        with konekcija.cursor() as kursor:
            kursor.execute(upit, (*vrednosti, vrednost_primarnog_kljuca))
            red_je_pronadjen = kursor.rowcount == 1

        konekcija.commit()

    return red_je_pronadjen


def obrisi_red(naziv_tabele: str, vrednost_primarnog_kljuca: int) -> bool:
    """Obrisi izabrani red i vrati da li je red pronadjen."""

    konfiguracija = _proveri_tabelu(naziv_tabele)
    upit = sql.SQL("DELETE FROM {} WHERE {} = %s;").format(
        sql.Identifier(naziv_tabele),
        sql.Identifier(konfiguracija["primarni_kljuc"]),
    )

    with closing(povezi_se()) as konekcija:
        with konekcija.cursor() as kursor:
            kursor.execute(upit, (vrednost_primarnog_kljuca,))
            red_je_pronadjen = kursor.rowcount == 1

        konekcija.commit()

    return red_je_pronadjen


def pronadji_zonu(oznaka: str) -> int:
    """Pronadji primarni kljuc zone prema njenoj oznaci."""

    with closing(povezi_se()) as konekcija, konekcija.cursor() as kursor:
        kursor.execute(
            "SELECT zona_id FROM zone_kampusa WHERE oznaka = %s;",
            (oznaka,),
        )
        red = kursor.fetchone()

    if red is None:
        raise ValueError(f"Zona sa oznakom '{oznaka}' ne postoji.")

    return red[0]
