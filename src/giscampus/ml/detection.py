"""Pokretanje detekcije zgrada i cuvanje dobijene maske."""

from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
import torch
from rasterio.features import geometry_mask

from src.giscampus.geo.data import PUTANJA_RASTERA_KAMPUSA

from .data import pocetne_pozicije, ucitaj_rgb_raster
from .model import KOREN_PROJEKTA, VELICINA_ISECKA, ucitaj_istrenirani_unet
from .visualization import napravi_pregled_detekcije

FOLDER_REZULTATA = KOREN_PROJEKTA / "data" / "ml" / "results"
PUTANJA_VEROVATNOCE = FOLDER_REZULTATA / "verovatnoca_zgrada.tif"
PUTANJA_MASKE = FOLDER_REZULTATA / "maska_zgrada.tif"
PUTANJA_PREGLEDA = FOLDER_REZULTATA / "pregled_detekcije.png"
PUTANJA_ZONA = KOREN_PROJEKTA / "data" / "processed" / "campus" / "zone.geojson"

PRAG_DETEKCIJE = 0.5
PREKLAPANJE = 64
VELICINA_PAKETA = 4


def _sacuvaj_geotiff(
    podaci: np.ndarray,
    profil: dict,
    putanja: Path,
    tip_podataka: str,
) -> Path:
    """Sacuvaj jedan kanal uz koordinatni sistem originalnog rastera."""

    putanja.parent.mkdir(parents=True, exist_ok=True)
    izlazni_profil = profil.copy()
    izlazni_profil.update(
        driver="GTiff",
        count=1,
        dtype=tip_podataka,
        compress="deflate",
    )
    with rasterio.open(putanja, "w", **izlazni_profil) as raster:
        raster.write(podaci.astype(tip_podataka), 1)
    return putanja


def _napravi_masku_zona(
    profil: dict,
    visina: int,
    sirina: int,
) -> np.ndarray:
    """Vrati masku piksela koji se nalaze unutar neke zone kampusa."""

    zone = gpd.read_file(PUTANJA_ZONA)
    if zone.empty:
        raise ValueError("Fajl sa zonama kampusa nema geometrije.")
    if zone.crs != profil["crs"]:
        zone = zone.to_crs(profil["crs"])

    geometrije = [
        geometrija.__geo_interface__
        for geometrija in zone.geometry
        if geometrija is not None and not geometrija.is_empty
    ]
    return geometry_mask(
        geometrije,
        out_shape=(visina, sirina),
        transform=profil["transform"],
        invert=True,
    )


def detektuj_zgrade(
    putanja_rastera: Path = PUTANJA_RASTERA_KAMPUSA,
    prag: float = PRAG_DETEKCIJE,
) -> dict[str, Path]:
    """Detektuj zgrade na celom rasteru pomocu preklopljenih iseckaka."""

    if not 0 < prag < 1:
        raise ValueError("Prag detekcije mora biti izmedju 0 i 1.")

    slika, profil = ucitaj_rgb_raster(putanja_rastera)
    visina, sirina = slika.shape[:2]
    korak = VELICINA_ISECKA - PREKLAPANJE
    x_pozicije = pocetne_pozicije(sirina, VELICINA_ISECKA, korak)
    y_pozicije = pocetne_pozicije(visina, VELICINA_ISECKA, korak)
    pozicije = [(x, y) for y in y_pozicije for x in x_pozicije]

    zbir_verovatnoca = np.zeros((visina, sirina), dtype=np.float32)
    broj_predvidjanja = np.zeros((visina, sirina), dtype=np.uint16)
    model = ucitaj_istrenirani_unet()

    for pocetak in range(0, len(pozicije), VELICINA_PAKETA):
        paket_pozicija = pozicije[pocetak : pocetak + VELICINA_PAKETA]
        isecak_paket = np.stack(
            [
                slika[
                    y : y + VELICINA_ISECKA,
                    x : x + VELICINA_ISECKA,
                ]
                for x, y in paket_pozicija
            ]
        )
        ulaz = torch.from_numpy(isecak_paket).permute(0, 3, 1, 2).float() / 255.0

        with torch.inference_mode():
            izlaz = model(ulaz)
            verovatnoce = torch.sigmoid(izlaz[:, 0]).cpu().numpy()

        for (x, y), verovatnoca in zip(
            paket_pozicija,
            verovatnoce,
            strict=True,
        ):
            zbir_verovatnoca[
                y : y + VELICINA_ISECKA,
                x : x + VELICINA_ISECKA,
            ] += verovatnoca
            broj_predvidjanja[
                y : y + VELICINA_ISECKA,
                x : x + VELICINA_ISECKA,
            ] += 1

    verovatnoca = zbir_verovatnoca / np.maximum(broj_predvidjanja, 1)
    maska_zona = _napravi_masku_zona(profil, visina, sirina)
    verovatnoca = np.where(maska_zona, verovatnoca, 0.0)
    maska = (verovatnoca >= prag).astype(np.uint8)

    _sacuvaj_geotiff(
        verovatnoca,
        profil,
        PUTANJA_VEROVATNOCE,
        "float32",
    )
    _sacuvaj_geotiff(
        maska,
        profil,
        PUTANJA_MASKE,
        "uint8",
    )
    napravi_pregled_detekcije(slika, maska, PUTANJA_PREGLEDA)

    return {
        "verovatnoca": PUTANJA_VEROVATNOCE,
        "maska": PUTANJA_MASKE,
        "pregled": PUTANJA_PREGLEDA,
    }


if __name__ == "__main__":
    rezultati = detektuj_zgrade()
    print("Detekcija zgrada je zavrsena:")
    for naziv, putanja in rezultati.items():
        print(f"- {naziv}: {putanja}")
