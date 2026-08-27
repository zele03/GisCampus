"""Preuzimanje, ucitavanje i priprema prostornih podataka."""

from pathlib import Path
from os import environ
from shutil import copyfileobj
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zipfile import ZipFile, is_zipfile

import geopandas as gpd
import pandas as pd
import rasterio
from rasterio.transform import from_bounds

GEOFABRIK_URL = "https://download.geofabrik.de/europe/serbia-latest-free.shp.zip"

KOREN_PROJEKTA = Path(__file__).resolve().parents[3]
FOLDER_VEKTORSKIH_PODATAKA = KOREN_PROJEKTA / "data" / "raw" / "vector"
PUTANJA_ARHIVE = FOLDER_VEKTORSKIH_PODATAKA / "serbia-latest-free.shp.zip"
FOLDER_GEOFABRIK_SRBIJA = FOLDER_VEKTORSKIH_PODATAKA / "geofabrik_serbia"
FOLDER_RASTERSKIH_PODATAKA = KOREN_PROJEKTA / "data" / "raw" / "raster"
PUTANJA_RASTERA_KAMPUSA = FOLDER_RASTERSKIH_PODATAKA / "kampus_esri.tif"

# Pravougaonik podrucja kampusa u Novom Sadu, u EPSG:4326 koordinatama.
OKVIR_KAMPUSA = (19.8470, 45.2425, 19.8590, 45.2500)

GEOFABRIK_SLOJEVI = {
    "zgrade": "gis_osm_buildings_a_free_1.shp",
    "putevi": "gis_osm_roads_free_1.shp",
    "namena_zemljista": "gis_osm_landuse_a_free_1.shp",
    "tackasti_objekti": "gis_osm_pois_free_1.shp",
    "poligonski_objekti": "gis_osm_pois_a_free_1.shp",
}

ESRI_WORLD_IMAGERY_EXPORT = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "World_Imagery/MapServer/export"
)


def preuzmi_geofabrik_shp() -> Path:
    """Preuzmi Geofabrik SHP arhivu za Srbiju ako vec nije preuzeta."""

    FOLDER_VEKTORSKIH_PODATAKA.mkdir(parents=True, exist_ok=True)

    if PUTANJA_ARHIVE.exists() and is_zipfile(PUTANJA_ARHIVE):
        return PUTANJA_ARHIVE

    privremena_putanja = PUTANJA_ARHIVE.with_suffix(".zip.part")
    zahtev = Request(GEOFABRIK_URL, headers={"User-Agent": "GisCampus/1.0"})

    with urlopen(zahtev) as odgovor, privremena_putanja.open("wb") as fajl:
        copyfileobj(odgovor, fajl)

    if not is_zipfile(privremena_putanja):
        raise RuntimeError("Preuzeti Geofabrik fajl nije ispravna ZIP arhiva.")

    privremena_putanja.replace(PUTANJA_ARHIVE)
    return PUTANJA_ARHIVE


def raspakuj_geofabrik_shp(putanja_arhive: Path = PUTANJA_ARHIVE) -> Path:
    """Bezbedno raspakuj Geofabrik arhivu i vrati folder sa podacima."""

    postojeci_slojevi = tuple(FOLDER_GEOFABRIK_SRBIJA.glob("*.shp"))
    if postojeci_slojevi:
        return FOLDER_GEOFABRIK_SRBIJA

    FOLDER_GEOFABRIK_SRBIJA.mkdir(parents=True, exist_ok=True)
    odredisni_folder = FOLDER_GEOFABRIK_SRBIJA.resolve()

    with ZipFile(putanja_arhive) as arhiva:
        for clan in arhiva.infolist():
            odrediste = (odredisni_folder / clan.filename).resolve()
            if not odrediste.is_relative_to(odredisni_folder):
                raise RuntimeError("Arhiva sadrzi nebezbednu putanju.")

        arhiva.extractall(odredisni_folder)

    return FOLDER_GEOFABRIK_SRBIJA


def pronadji_shp_slojeve(folder: Path = FOLDER_GEOFABRIK_SRBIJA) -> tuple[Path, ...]:
    """Vrati sortirane putanje svih SHP slojeva iz zadatog foldera."""

    return tuple(sorted(folder.rglob("*.shp")))


def pripremi_geofabrik_podatke() -> tuple[Path, ...]:
    """Preuzmi i raspakuj Geofabrik podatke, pa vrati SHP slojeve."""

    putanja_arhive = preuzmi_geofabrik_shp()
    folder = raspakuj_geofabrik_shp(putanja_arhive)
    slojevi = pronadji_shp_slojeve(folder)

    if not slojevi:
        raise RuntimeError("U Geofabrik arhivi nisu pronadjeni SHP slojevi.")

    return slojevi


def ucitaj_shp_sloj(
    naziv_sloja: str,
    okvir: tuple[float, float, float, float] = OKVIR_KAMPUSA,
) -> gpd.GeoDataFrame:
    """Ucitaj izabrani SHP sloj samo za siri okvir oko kampusa."""

    if naziv_sloja not in GEOFABRIK_SLOJEVI:
        raise ValueError(f"Geofabrik sloj '{naziv_sloja}' nije definisan.")

    pripremi_geofabrik_podatke()
    putanja_sloja = FOLDER_GEOFABRIK_SRBIJA / GEOFABRIK_SLOJEVI[naziv_sloja]

    if not putanja_sloja.exists():
        raise FileNotFoundError(f"SHP sloj nije pronadjen: {putanja_sloja}")

    return gpd.read_file(putanja_sloja, bbox=okvir, engine="pyogrio")


def ucitaj_geofabrik_slojeve() -> dict[str, gpd.GeoDataFrame]:
    """Ucitaj svih pet izabranih slojeva u zasebne GeoDataFrame objekte."""

    return {naziv: ucitaj_shp_sloj(naziv) for naziv in GEOFABRIK_SLOJEVI}


def napravi_dataframe(geo_dataframe: gpd.GeoDataFrame) -> pd.DataFrame:
    """Pretvori GeoDataFrame u pandas DataFrame i zadrzi sve kolone."""

    return pd.DataFrame(geo_dataframe.copy())


def napravi_dataframe_slojeve() -> dict[str, pd.DataFrame]:
    """Napravi pandas DataFrame za svaki ucitani Geofabrik SHP sloj."""

    geo_slojevi = ucitaj_geofabrik_slojeve()
    return {
        naziv: napravi_dataframe(geo_dataframe)
        for naziv, geo_dataframe in geo_slojevi.items()
    }


def preuzmi_raster_kampusa(
    putanja: Path = PUTANJA_RASTERA_KAMPUSA,
    okvir: tuple[float, float, float, float] = OKVIR_KAMPUSA,
) -> Path:
    """Preuzmi Esri World Imagery i sacuvaj ga kao georeferencirani TIFF."""

    if putanja.exists() and putanja.stat().st_size > 0:
        return putanja

    putanja.parent.mkdir(parents=True, exist_ok=True)
    privremena_putanja = putanja.with_suffix(".tif.part")
    parametri = urlencode(
        {
            "bbox": ",".join(map(str, okvir)),
            "bboxSR": "4326",
            "imageSR": "4326",
            "size": "2400,1500",
            "format": "tiff",
            "f": "image",
        }
    )
    zahtev = Request(
        f"{ESRI_WORLD_IMAGERY_EXPORT}?{parametri}",
        headers={"User-Agent": "GisCampus/1.0"},
    )

    with urlopen(zahtev, timeout=120) as odgovor, privremena_putanja.open("wb") as fajl:
        copyfileobj(odgovor, fajl)

    # PostgreSQL na Windowsu moze postaviti PROJ putanju koja nije kompatibilna
    # sa Rasterio bibliotekom, pa ovde biramo PROJ podatke iz virtuelnog okruzenja.
    proj_folder = Path(rasterio.__file__).resolve().parent / "proj_data"
    environ["PROJ_LIB"] = str(proj_folder)
    environ["PROJ_DATA"] = str(proj_folder)

    with rasterio.open(privremena_putanja) as izvor:
        profil = izvor.profile.copy()
        profil.update(
            driver="GTiff",
            crs="EPSG:4326",
            transform=from_bounds(*okvir, izvor.width, izvor.height),
        )
        podaci = izvor.read()

    with rasterio.open(putanja, "w", **profil) as odrediste:
        odrediste.write(podaci)
        odrediste.update_tags(
            izvor="Esri World Imagery",
            autorska_prava="Esri i dobavljaci snimaka",
        )

    privremena_putanja.unlink(missing_ok=True)
    return putanja
