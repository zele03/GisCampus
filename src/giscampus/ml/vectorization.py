"""Pretvaranje maske detektovanih zgrada u vektorske poligone."""

from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from psycopg2 import Binary
from rasterio.features import shapes
from rasterio.mask import mask as iseci_raster
from shapely.geometry import shape

from .detection import PUTANJA_MASKE, PUTANJA_VEROVATNOCE, PUTANJA_ZONA
from .model import KOREN_PROJEKTA
from src.giscampus.sql.database import kreiraj_tabele, povezi_se

PUTANJA_VEKTORA = KOREN_PROJEKTA / "data" / "ml" / "results" / "ml_zgrade.geojson"
MINIMALNA_POVRSINA_M2 = 20.0
EPSG_PROJEKTA = 32634


def _prosecna_pouzdanost(
    raster_verovatnoce: rasterio.io.DatasetReader,
    geometrija: dict,
) -> float:
    """Izracunaj prosecnu verovatnocu unutar jednog detektovanog poligona."""

    vrednosti, _ = iseci_raster(
        raster_verovatnoce,
        [geometrija],
        crop=True,
        filled=False,
    )
    return float(vrednosti[0].mean())


def vektorizuj_detekcije(
    minimalna_povrsina_m2: float = MINIMALNA_POVRSINA_M2,
    putanja_izlaza: Path = PUTANJA_VEKTORA,
) -> gpd.GeoDataFrame:
    """Pretvori masku u ociscene poligone i dodeli im zone kampusa."""

    if minimalna_povrsina_m2 <= 0:
        raise ValueError("Minimalna povrsina mora biti veca od nule.")

    redovi = []
    with (
        rasterio.open(PUTANJA_MASKE) as raster_maske,
        rasterio.open(PUTANJA_VEROVATNOCE) as raster_verovatnoce,
    ):
        maska = raster_maske.read(1)
        for geometrija, vrednost in shapes(
            maska,
            mask=maska == 1,
            transform=raster_maske.transform,
        ):
            if int(vrednost) != 1:
                continue
            redovi.append(
                {
                    "pouzdanost": _prosecna_pouzdanost(
                        raster_verovatnoce,
                        geometrija,
                    ),
                    "geometry": shape(geometrija),
                }
            )
        crs_rastera = raster_maske.crs

    detekcije = gpd.GeoDataFrame(redovi, geometry="geometry", crs=crs_rastera)
    detekcije = detekcije.to_crs(EPSG_PROJEKTA)
    detekcije = detekcije.explode(index_parts=False, ignore_index=True)
    detekcije["geometry"] = detekcije.geometry.simplify(
        tolerance=0.35,
        preserve_topology=True,
    )
    detekcije["povrsina_m2"] = detekcije.geometry.area
    detekcije = detekcije[
        detekcije["povrsina_m2"] >= minimalna_povrsina_m2
    ].copy()

    zone = gpd.read_file(PUTANJA_ZONA).to_crs(EPSG_PROJEKTA)
    zone = zone[["naziv", "geometry"]].rename(columns={"naziv": "zona"})
    detekcije["_indeks_detekcije"] = detekcije.index
    preseci = gpd.overlay(
        detekcije,
        zone,
        how="intersection",
        keep_geom_type=True,
    )
    preseci["povrsina_preseka"] = preseci.geometry.area
    najveci_preseci = (
        preseci.sort_values("povrsina_preseka", ascending=False)
        .drop_duplicates("_indeks_detekcije")
        .set_index("_indeks_detekcije")["zona"]
    )
    detekcije["zona"] = detekcije["_indeks_detekcije"].map(najveci_preseci)
    detekcije = detekcije.dropna(subset=["zona"]).copy()
    detekcije = detekcije.drop(columns="_indeks_detekcije")
    detekcije["povrsina_m2"] = detekcije["povrsina_m2"].round(2)
    detekcije["pouzdanost"] = detekcije["pouzdanost"].round(4)
    detekcije["status_provere"] = "nije_potvrdjeno"
    detekcije.insert(0, "detekcija_id", np.arange(1, len(detekcije) + 1))
    detekcije = detekcije[
        [
            "detekcija_id",
            "zona",
            "povrsina_m2",
            "pouzdanost",
            "status_provere",
            "geometry",
        ]
    ]

    putanja_izlaza.parent.mkdir(parents=True, exist_ok=True)
    detekcije.to_crs(4326).to_file(putanja_izlaza, driver="GeoJSON")
    return detekcije


def upisi_u_postgis(
    detekcije: gpd.GeoDataFrame,
    zameni_postojece: bool = False,
) -> int:
    """Upisi ML poligone i po zahtevu bezbedno zameni nepotvrdjene rezultate."""

    kreiraj_tabele()
    with povezi_se() as konekcija, konekcija.cursor() as kursor:
        kursor.execute("SELECT COUNT(*) FROM ml_zgrade;")
        postojeci_broj = kursor.fetchone()[0]
        if postojeci_broj and not zameni_postojece:
            return postojeci_broj
        if postojeci_broj:
            kursor.execute(
                """
                SELECT COUNT(*)
                FROM ml_zgrade
                WHERE status_provere <> 'nije_potvrdjeno';
                """
            )
            if kursor.fetchone()[0]:
                raise ValueError(
                    "ML rezultati sa rucno promenjenim statusom ne smeju se zameniti."
                )
            kursor.execute("TRUNCATE TABLE ml_zgrade RESTART IDENTITY;")

        kursor.execute("SELECT zona_id, naziv FROM zone_kampusa;")
        zone_po_nazivu = {naziv: zona_id for zona_id, naziv in kursor.fetchall()}
        nepoznate_zone = set(detekcije["zona"]) - set(zone_po_nazivu)
        if nepoznate_zone:
            raise ValueError(
                "U bazi nisu pronadjene zone: " + ", ".join(sorted(nepoznate_zone))
            )

        for red in detekcije.itertuples(index=False):
            kursor.execute(
                """
                INSERT INTO ml_zgrade (
                    zona_id,
                    povrsina_m2,
                    pouzdanost,
                    status_provere,
                    geometrija
                )
                VALUES (%s, %s, %s, %s, ST_GeomFromWKB(%s, 32634));
                """,
                (
                    zone_po_nazivu[red.zona],
                    float(red.povrsina_m2),
                    float(red.pouzdanost),
                    red.status_provere,
                    Binary(red.geometry.wkb),
                ),
            )
        konekcija.commit()
    return len(detekcije)


if __name__ == "__main__":
    rezultat = vektorizuj_detekcije()
    broj_u_bazi = upisi_u_postgis(rezultat)
    print(f"Vektorizacija je zavrsena. Broj ML poligona: {len(rezultat)}")
    print(f"Broj redova u PostGIS tabeli ml_zgrade: {broj_u_bazi}")
    print(f"Rezultat: {PUTANJA_VEKTORA}")
