"""Prikaz ulaznog snimka, maske i detektovanih zgrada radi provere."""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def napravi_pregled_detekcije(
    slika: np.ndarray,
    maska: np.ndarray,
    putanja: Path,
    sirina_panela: int = 1000,
) -> Path:
    """Sacuvaj original, crveni preklop i binarnu masku u jednoj slici."""

    original = Image.fromarray(slika)
    odnos = sirina_panela / original.width
    visina_panela = round(original.height * odnos)
    dimenzije = (sirina_panela, visina_panela)
    original = original.resize(dimenzije, Image.Resampling.LANCZOS)

    maska_slika = Image.fromarray((maska * 255).astype(np.uint8)).resize(
        dimenzije,
        Image.Resampling.NEAREST,
    )
    boja_detekcije = Image.new("RGB", dimenzije, (0, 230, 255))
    preklop = Image.composite(boja_detekcije, original, maska_slika)
    preklop = Image.blend(original, preklop, alpha=0.55)
    crno_bela = Image.merge("RGB", (maska_slika, maska_slika, maska_slika))

    visina_naslova = 40
    pregled = Image.new(
        "RGB",
        (sirina_panela * 3, visina_panela + visina_naslova),
        "white",
    )
    crtanje = ImageDraw.Draw(pregled)
    naslovi = ("Originalni raster", "Detektovane zgrade", "Binarna maska")
    paneli = (original, preklop, crno_bela)
    for indeks, (naslov, panel) in enumerate(zip(naslovi, paneli, strict=True)):
        x = indeks * sirina_panela
        crtanje.text((x + 12, 12), naslov, fill="black")
        pregled.paste(panel, (x, visina_naslova))

    putanja.parent.mkdir(parents=True, exist_ok=True)
    pregled.save(putanja)
    return putanja
