"""Ucitavanje lokalnih podesavanja projekta."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class PodesavanjaBaze:
    """Parametri potrebni za povezivanje sa PostgreSQL bazom."""

    host: str
    port: int
    naziv_baze: str
    korisnik: str
    lozinka: str


def ucitaj_podesavanja_baze() -> PodesavanjaBaze:
    """Ucitaj i proveri parametre baze iz lokalnog .env fajla."""

    load_dotenv()

    obavezne_promenljive = ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD")
    nedostaju = [naziv for naziv in obavezne_promenljive if not os.getenv(naziv)]

    if nedostaju:
        raise ValueError(
            "Nedostaju obavezne promenljive u .env fajlu: " + ", ".join(nedostaju)
        )

    return PodesavanjaBaze(
        host=os.environ["DB_HOST"],
        port=int(os.environ["DB_PORT"]),
        naziv_baze=os.environ["DB_NAME"],
        korisnik=os.environ["DB_USER"],
        lozinka=os.environ["DB_PASSWORD"],
    )
