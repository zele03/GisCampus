"""Ucitavanje i priprema snimaka za detekciju zgrada."""

from pathlib import Path

import numpy as np
import rasterio


def ucitaj_rgb_raster(putanja: Path) -> tuple[np.ndarray, dict]:
    """Ucitaj prva tri kanala rastera kao RGB sliku i sacuvaj njen profil."""

    with rasterio.open(putanja) as raster:
        if raster.count < 3:
            raise ValueError("Raster mora imati najmanje tri RGB kanala.")
        slika = np.moveaxis(raster.read([1, 2, 3]), 0, 2)
        profil = raster.profile.copy()

    if slika.dtype != np.uint8:
        slika = np.clip(slika, 0, 255).astype(np.uint8)
    return slika, profil


def pocetne_pozicije(duzina: int, velicina: int, korak: int) -> list[int]:
    """Vrati pozicije isecka tako da bude pokriven i kraj slike."""

    if duzina <= velicina:
        return [0]

    pozicije = list(range(0, duzina - velicina + 1, korak))
    poslednja = duzina - velicina
    if pozicije[-1] != poslednja:
        pozicije.append(poslednja)
    return pozicije
