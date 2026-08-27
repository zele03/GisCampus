"""Overlay tehnike i prostorni upiti nad geoprostornim podacima."""

from pathlib import Path
from warnings import catch_warnings, simplefilter

import geopandas as gpd
from psycopg2 import Binary
from shapely.ops import polygonize, unary_union

from ..sql.database import povezi_se
from .data import KOREN_PROJEKTA

PUTANJA_NACRTANIH_ZONA = (
    KOREN_PROJEKTA / "data" / "processed" / "campus" / "zone_nacrtane.geojson"
)
PUTANJA_ZONA = (
    KOREN_PROJEKTA / "data" / "processed" / "campus" / "zone.geojson"
)
PUTANJA_PARKIRALISTA = (
    KOREN_PROJEKTA / "data" / "processed" / "campus" / "parkiralista.geojson"
)
PUTANJA_ZELENIH_POVRSINA = (
    KOREN_PROJEKTA
    / "data"
    / "processed"
    / "campus"
    / "zelene_povrsine.geojson"
)
PUTANJA_INFRASTRUKTURNIH_OBJEKATA = (
    KOREN_PROJEKTA
    / "data"
    / "processed"
    / "campus"
    / "infrastrukturni_objekti.geojson"
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


def upisi_parkiralista_u_postgis(
    putanja: Path = PUTANJA_PARKIRALISTA,
) -> int:
    """Povezi nacrtane poligone sa SQL parkiralistima i upisi ih u bazu."""

    parkiralista = gpd.read_file(putanja).to_crs(32634)
    ocekivani_id = set(range(1, 13))

    if set(parkiralista["parkiraliste_id"].astype(int)) != ocekivani_id:
        raise ValueError("GeoJSON mora sadrzati parkiraliste_id vrednosti od 1 do 12.")
    if not parkiralista.geometry.is_valid.all():
        raise ValueError("Sve geometrije parkiralista moraju biti ispravne.")

    broj_azuriranih = 0
    with povezi_se() as konekcija, konekcija.cursor() as kursor:
        for _, parkiraliste in parkiralista.iterrows():
            kursor.execute(
                """
                UPDATE parkiralista
                SET povrsina_m2 = %s,
                    geometrija = ST_GeomFromWKB(%s, 32634)
                WHERE parkiraliste_id = %s AND naziv = %s;
                """,
                (
                    round(parkiraliste.geometry.area, 2),
                    Binary(parkiraliste.geometry.wkb),
                    int(parkiraliste["parkiraliste_id"]),
                    parkiraliste["naziv"],
                ),
            )
            broj_azuriranih += kursor.rowcount

        if broj_azuriranih != 12:
            raise RuntimeError(
                "Ocekivano je 12 azuriranih parkiralista, "
                f"a dobijeno {broj_azuriranih}."
            )

    return broj_azuriranih


def upisi_zelene_povrsine_u_postgis(
    putanja: Path = PUTANJA_ZELENIH_POVRSINA,
) -> int:
    """Povezi nacrtane zelene povrsine sa SQL redovima i upisi ih u bazu."""

    zelene_povrsine = gpd.read_file(putanja).to_crs(32634)
    ocekivani_id = set(range(1, 6))

    if set(zelene_povrsine["zelena_povrsina_id"].astype(int)) != ocekivani_id:
        raise ValueError(
            "GeoJSON mora sadrzati zelena_povrsina_id vrednosti od 1 do 5."
        )
    if not zelene_povrsine.geometry.is_valid.all():
        raise ValueError("Sve geometrije zelenih povrsina moraju biti ispravne.")

    broj_azuriranih = 0
    with povezi_se() as konekcija, konekcija.cursor() as kursor:
        for _, povrsina in zelene_povrsine.iterrows():
            kursor.execute(
                """
                UPDATE zelene_povrsine
                SET povrsina_m2 = %s,
                    geometrija = ST_GeomFromWKB(%s, 32634)
                WHERE zelena_povrsina_id = %s AND tip = %s;
                """,
                (
                    round(povrsina.geometry.area, 2),
                    Binary(povrsina.geometry.wkb),
                    int(povrsina["zelena_povrsina_id"]),
                    povrsina["tip"],
                ),
            )
            broj_azuriranih += kursor.rowcount

        if broj_azuriranih != 5:
            raise RuntimeError(
                "Ocekivano je pet azuriranih zelenih povrsina, "
                f"a dobijeno {broj_azuriranih}."
            )

    return broj_azuriranih


def upisi_infrastrukturne_objekte_u_postgis(
    putanja: Path = PUTANJA_INFRASTRUKTURNIH_OBJEKATA,
) -> int:
    """Povezi nacrtane tacke sa SQL infrastrukturnim objektima."""

    objekti = gpd.read_file(putanja).to_crs(32634)
    ocekivani_id = set(range(1, 7))

    if set(objekti["infrastrukturni_objekat_id"].astype(int)) != ocekivani_id:
        raise ValueError(
            "GeoJSON mora sadrzati infrastrukturni_objekat_id vrednosti od 1 do 6."
        )
    if not objekti.geometry.is_valid.all():
        raise ValueError("Sve tacke infrastrukturnih objekata moraju biti ispravne.")
    if not (objekti.geometry.geom_type == "Point").all():
        raise ValueError("Sve geometrije infrastrukturnih objekata moraju biti tacke.")

    broj_azuriranih = 0
    with povezi_se() as konekcija, konekcija.cursor() as kursor:
        for _, objekat in objekti.iterrows():
            kursor.execute(
                """
                UPDATE infrastrukturni_objekti
                SET geometrija = ST_GeomFromWKB(%s, 32634)
                WHERE infrastrukturni_objekat_id = %s AND naziv = %s;
                """,
                (
                    Binary(objekat.geometry.wkb),
                    int(objekat["infrastrukturni_objekat_id"]),
                    objekat["naziv"],
                ),
            )
            broj_azuriranih += kursor.rowcount

        if broj_azuriranih != 6:
            raise RuntimeError(
                "Ocekivano je sest azuriranih infrastrukturnih objekata, "
                f"a dobijeno {broj_azuriranih}."
            )

    return broj_azuriranih


def upisi_terene_u_postgis() -> int:
    """Povezi OSM poligone sa SQL terenima i upisi geometrije i povrsine."""

    # Uvoz je unutar funkcije iz istog razloga kao kod obrade zgrada.
    from .map import pripremi_predloge_terena

    tereni = pripremi_predloge_terena().to_crs(32634)
    if len(tereni) != 8:
        raise ValueError("Ocekivano je tacno osam pripremljenih terena.")
    if not tereni.geometry.is_valid.all():
        raise ValueError("Sve geometrije terena moraju biti ispravne.")
    if not (tereni.geometry.geom_type == "Polygon").all():
        raise ValueError("Sve geometrije terena moraju biti poligoni.")

    broj_azuriranih = 0
    with povezi_se() as konekcija, konekcija.cursor() as kursor:
        for _, teren in tereni.iterrows():
            kursor.execute(
                """
                UPDATE tereni
                SET povrsina_m2 = %s,
                    geometrija = ST_GeomFromWKB(%s, 32634)
                WHERE naziv = %s;
                """,
                (
                    round(teren["geometrija"].area, 2),
                    Binary(teren["geometrija"].wkb),
                    teren["naziv"],
                ),
            )
            broj_azuriranih += kursor.rowcount

        if broj_azuriranih != 8:
            raise RuntimeError(
                "Ocekivano je osam azuriranih terena, "
                f"a dobijeno {broj_azuriranih}."
            )

    return broj_azuriranih


UPITI_SLOJEVA_ZA_ANALIZE = {
    "zone": """
        SELECT zona_id, naziv, geometrija
        FROM zone_kampusa WHERE geometrija IS NOT NULL;
    """,
    "zgrade": """
        SELECT zgrada_id, zona_id, naziv, geometrija
        FROM zgrade WHERE geometrija IS NOT NULL;
    """,
    "parkiralista": """
        SELECT parkiraliste_id, zona_id, naziv, geometrija
        FROM parkiralista WHERE geometrija IS NOT NULL;
    """,
    "zelene_povrsine": """
        SELECT zelena_povrsina_id, zona_id, tip, geometrija
        FROM zelene_povrsine WHERE geometrija IS NOT NULL;
    """,
    "infrastrukturni_objekti": """
        SELECT infrastrukturni_objekat_id, zona_id, naziv, geometrija
        FROM infrastrukturni_objekti WHERE geometrija IS NOT NULL;
    """,
}


def ucitaj_sloj_za_analizu(naziv_sloja: str) -> gpd.GeoDataFrame:
    """Ucitaj jedan projektni sloj iz PostGIS baze u EPSG:32634."""

    if naziv_sloja not in UPITI_SLOJEVA_ZA_ANALIZE:
        raise ValueError(f"Sloj '{naziv_sloja}' nije podrzan za analize.")

    with povezi_se() as konekcija, catch_warnings():
        simplefilter("ignore", UserWarning)
        sloj = gpd.read_postgis(
            UPITI_SLOJEVA_ZA_ANALIZE[naziv_sloja],
            konekcija,
            geom_col="geometrija",
            crs="EPSG:32634",
        )

    return sloj.rename_geometry("geometry")


def analiza_clip_zgrada() -> gpd.GeoDataFrame:
    """CLIP: odseci zgrade granicom Severne zone kampusa."""

    zone = ucitaj_sloj_za_analizu("zone")
    zgrade = ucitaj_sloj_za_analizu("zgrade")
    severna_zona = zone[zone["naziv"] == "Severna"][["geometry"]]
    if len(severna_zona) != 1:
        raise RuntimeError("U bazi mora postojati tacno jedna Severna zona.")

    rezultat = gpd.clip(zgrade, severna_zona)
    rezultat["analiza"] = "Zgrada unutar Severne zone"
    return rezultat


def analiza_preseka_parkinga_i_zelenila() -> gpd.GeoDataFrame:
    """INTERSECTION: izdvoji preseke parkiralista i zelenih povrsina."""

    parkiralista = ucitaj_sloj_za_analizu("parkiralista")
    zelenilo = ucitaj_sloj_za_analizu("zelene_povrsine")
    rezultat = gpd.overlay(
        parkiralista[["parkiraliste_id", "naziv", "geometry"]],
        zelenilo[["zelena_povrsina_id", "tip", "geometry"]],
        how="intersection",
        keep_geom_type=False,
    )
    rezultat["analiza"] = "Presek parkiralista i zelene povrsine"
    return rezultat


def analiza_unije_parkinga_i_zelenila() -> gpd.GeoDataFrame:
    """UNION: kombinuj parkiralista i zelene povrsine."""

    parkiralista = ucitaj_sloj_za_analizu("parkiralista")
    zelenilo = ucitaj_sloj_za_analizu("zelene_povrsine")
    rezultat = gpd.overlay(
        parkiralista[["parkiraliste_id", "naziv", "geometry"]],
        zelenilo[["zelena_povrsina_id", "tip", "geometry"]],
        how="union",
        keep_geom_type=False,
    )
    rezultat["analiza"] = "Unija parkiralista i zelenih povrsina"
    return rezultat


def analiza_slobodne_povrsine_kampusa() -> gpd.GeoDataFrame:
    """DIFFERENCE: oduzmi zgrade od ukupne povrsine kampusa."""

    zone = ucitaj_sloj_za_analizu("zone")
    zgrade = ucitaj_sloj_za_analizu("zgrade")
    kampus = zone[["geometry"]].dissolve().assign(naziv="Slobodna povrsina kampusa")
    zauzeto = zgrade[["geometry"]].dissolve()
    rezultat = gpd.overlay(kampus, zauzeto, how="difference")
    rezultat["povrsina_m2"] = rezultat.geometry.area.round(2)
    rezultat["analiza"] = "Povrsina kampusa bez zgrada"
    return rezultat


def analiza_buffera_infrastrukture() -> gpd.GeoDataFrame:
    """BUFFER: napravi zonu od 30 metara oko infrastrukturnih objekata."""

    objekti = ucitaj_sloj_za_analizu("infrastrukturni_objekti")
    rezultat = objekti.copy()
    rezultat.geometry = rezultat.geometry.buffer(30)
    rezultat["udaljenost_m"] = 30
    rezultat["analiza"] = "Buffer 30 m oko infrastrukturnog objekta"
    return rezultat


def analiza_infrastrukture_u_centralnoj_zoni() -> gpd.GeoDataFrame:
    """WITHIN: izdvoji infrastrukturu koja se nalazi u Centralnoj zoni."""

    zone = ucitaj_sloj_za_analizu("zone")
    centralna_zona = zone[zone["naziv"] == "Centralna"]
    if len(centralna_zona) != 1:
        raise RuntimeError("U bazi mora postojati tacno jedna Centralna zona.")

    objekti = ucitaj_sloj_za_analizu("infrastrukturni_objekti")
    geometrija_zone = centralna_zona.geometry.iloc[0]
    rezultat = objekti[objekti.geometry.within(geometrija_zone)].copy()
    rezultat["analiza"] = "Infrastrukturni objekat je u Centralnoj zoni"
    return rezultat


def analiza_preklapanja_parkinga_i_zgrada() -> gpd.GeoDataFrame:
    """OVERLAPS: pronadji parkiralista koja se preklapaju sa zgradama."""

    parkiralista = ucitaj_sloj_za_analizu("parkiralista")
    zgrade = ucitaj_sloj_za_analizu("zgrade")
    rezultat = gpd.sjoin(
        parkiralista,
        zgrade[["zgrada_id", "naziv", "geometry"]],
        how="inner",
        predicate="overlaps",
        lsuffix="parking",
        rsuffix="zgrada",
    )
    rezultat["analiza"] = "Parking se preklapa sa zgradom"
    return rezultat
