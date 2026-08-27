"""Overlay tehnike i prostorni upiti nad geoprostornim podacima."""

from pathlib import Path

import geopandas as gpd
from psycopg2 import Binary
from shapely.ops import polygonize, unary_union

from .data import KOREN_PROJEKTA
from ..sql.database import povezi_se

PUTANJA_NACRTANIH_ZONA = (
    KOREN_PROJEKTA / "data" / "processed" / "campus" / "zone_nacrtane.geojson"
)
PUTANJA_ZONA = (
    KOREN_PROJEKTA / "data" / "processed" / "campus" / "zone.geojson"
)


def ocisti_zone(
    ulazna_putanja: Path = PUTANJA_NACRTANIH_ZONA,
    izlazna_putanja: Path = PUTANJA_ZONA,
) -> gpd.GeoDataFrame:
    """Pretvori rucne crteze u podelu kampusa bez rupa i preklapanja."""

    nacrtano = gpd.read_file(ulazna_putanja).to_crs(32634)
    okvir_redovi = nacrtano[nacrtano["naziv"] == "okvir_kampusa"]
    zone = nacrtano[nacrtano["naziv"] != "okvir_kampusa"].copy()

    if len(okvir_redovi) != 1 or len(zone) != 5:
        raise ValueError("Potrebni su jedan okvir kampusa i tacno pet zona.")
    if not nacrtano.geometry.is_valid.all():
        raise ValueError("Svi nacrtani poligoni moraju biti geometrijski ispravni.")

    okvir = okvir_redovi.geometry.iloc[0]
    linije = unary_union([okvir.boundary, *zone.geometry.boundary.to_list()])
    delovi = [deo.intersection(okvir) for deo in polygonize(linije)]
    delovi = [deo for deo in delovi if not deo.is_empty and deo.area > 0.01]
    dodeljeni_delovi = {naziv: [] for naziv in zone["naziv"]}

    for deo in delovi:
        tacka = deo.representative_point()
        kandidati = []

        for _, zona in zone.iterrows():
            presek = deo.intersection(zona.geometry).area
            rastojanje = tacka.distance(zona.geometry.centroid)
            kandidati.append((presek, -rastojanje, zona["naziv"]))

        _, _, izabrani_naziv = max(kandidati)
        dodeljeni_delovi[izabrani_naziv].append(deo)

    redovi = []
    for naziv, geometrije in dodeljeni_delovi.items():
        if not geometrije:
            raise RuntimeError(f"Zona '{naziv}' nije dobila nijedan deo kampusa.")
        redovi.append({"naziv": naziv, "geometry": unary_union(geometrije)})

    ociscene = gpd.GeoDataFrame(redovi, geometry="geometry", crs=32634)
    ociscene["povrsina_m2"] = ociscene.geometry.area.round(2)
    ociscene = ociscene.to_crs(4326)

    izlazna_putanja.parent.mkdir(parents=True, exist_ok=True)
    ociscene.to_file(izlazna_putanja, driver="GeoJSON")
    return ociscene


def upisi_zone_u_postgis(
    putanja: Path = PUTANJA_ZONA,
) -> int:
    """Povezi ociscene poligone sa SQL zonama i upisi geometrije i povrsine."""

    zone = gpd.read_file(putanja).to_crs(32634)
    ocekivani_nazivi = {"Severna", "Juzna", "Istocna", "Zapadna", "Centralna"}

    if set(zone["naziv"]) != ocekivani_nazivi:
        raise ValueError("Ocisceni fajl mora sadrzati svih pet zona kampusa.")
    if not zone.geometry.is_valid.all():
        raise ValueError("Sve geometrije zona moraju biti ispravne.")

    broj_azuriranih = 0
    with povezi_se() as konekcija, konekcija.cursor() as kursor:
        for _, zona in zone.iterrows():
            kursor.execute(
                """
                UPDATE zone_kampusa
                SET povrsina_m2 = %s,
                    geometrija = ST_GeomFromWKB(%s, 32634)
                WHERE naziv = %s;
                """,
                (
                    round(zona.geometry.area, 2),
                    Binary(zona.geometry.wkb),
                    zona["naziv"],
                ),
            )
            broj_azuriranih += kursor.rowcount

        if broj_azuriranih != 5:
            raise RuntimeError(
                f"Ocekivano je pet azuriranih zona, a dobijeno {broj_azuriranih}."
            )

    return broj_azuriranih


def upisi_zgrade_u_postgis() -> int:
    """Povezi OSM poligone sa SQL zgradama i upisi geometrije i povrsine."""

    # Uvoz je unutar funkcije da modul za prikaz mape ne bi bio obavezno
    # ucitan pri ostalim prostornim analizama.
    from .map import pripremi_predloge_zgrada

    zgrade = pripremi_predloge_zgrada().to_crs(32634)
    if len(zgrade) != 14:
        raise ValueError("Ocekivano je tacno 14 pripremljenih zgrada.")
    if not zgrade.geometry.is_valid.all():
        raise ValueError("Sve geometrije zgrada moraju biti ispravne.")

    broj_azuriranih = 0
    with povezi_se() as konekcija, konekcija.cursor() as kursor:
        for _, zgrada in zgrade.iterrows():
            kursor.execute(
                """
                UPDATE zgrade
                SET povrsina_m2 = %s,
                    geometrija = ST_GeomFromWKB(%s, 32634)
                WHERE naziv = %s;
                """,
                (
                    round(zgrada["geometrija"].area, 2),
                    Binary(zgrada["geometrija"].wkb),
                    zgrada["naziv"],
                ),
            )
            broj_azuriranih += kursor.rowcount

        if broj_azuriranih != 14:
            raise RuntimeError(
                f"Ocekivano je 14 azuriranih zgrada, a dobijeno {broj_azuriranih}."
            )

    return broj_azuriranih
