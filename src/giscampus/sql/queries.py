"""JOIN i WHERE upiti nad podacima univerzitetskog kampusa."""

import pandas as pd
from sqlalchemy import URL, create_engine, text

from ..config import ucitaj_podesavanja_baze

SQL_UPITI = {
    "zgrade_u_centralnoj_zoni": {
        "sql": """
            SELECT
                z.zgrada_id,
                z.naziv AS zgrada,
                z.tip,
                zk.naziv AS zona
            FROM zgrade AS z
            JOIN zone_kampusa AS zk ON z.zona_id = zk.zona_id
            WHERE zk.oznaka = :oznaka
            ORDER BY z.naziv;
        """,
        "parametri": {"oznaka": "C"},
    },
    "fakulteti_u_kampusu": {
        "sql": """
            SELECT
                z.zgrada_id,
                z.naziv AS fakultet,
                zk.naziv AS zona
            FROM zgrade AS z
            JOIN zone_kampusa AS zk ON z.zona_id = zk.zona_id
            WHERE z.tip = :tip
            ORDER BY zk.naziv, z.naziv;
        """,
        "parametri": {"tip": "fakultet"},
    },
    "javna_parkiralista": {
        "sql": """
            SELECT
                p.parkiraliste_id,
                p.tip,
                zk.naziv AS zona
            FROM parkiralista AS p
            JOIN zone_kampusa AS zk ON p.zona_id = zk.zona_id
            WHERE p.tip = :tip
            ORDER BY zk.naziv, p.parkiraliste_id;
        """,
        "parametri": {"tip": "javno"},
    },
    "zelene_povrsine_u_istocnoj_zoni": {
        "sql": """
            SELECT
                zp.zelena_povrsina_id,
                zp.tip,
                zk.naziv AS zona
            FROM zelene_povrsine AS zp
            JOIN zone_kampusa AS zk ON zp.zona_id = zk.zona_id
            WHERE zk.oznaka = :oznaka
            ORDER BY zp.zelena_povrsina_id;
        """,
        "parametri": {"oznaka": "I"},
    },
    "neispravni_infrastrukturni_objekti": {
        "sql": """
            SELECT
                io.infrastrukturni_objekat_id,
                io.naziv AS objekat,
                io.stanje,
                zk.naziv AS zona
            FROM infrastrukturni_objekti AS io
            JOIN zone_kampusa AS zk ON io.zona_id = zk.zona_id
            WHERE io.stanje = :stanje
            ORDER BY io.naziv;
        """,
        "parametri": {"stanje": "neispravno"},
    },
    "tereni_u_juznoj_zoni": {
        "sql": """
            SELECT
                t.teren_id,
                t.naziv AS teren,
                zk.naziv AS zona
            FROM tereni AS t
            JOIN zone_kampusa AS zk ON t.zona_id = zk.zona_id
            WHERE zk.oznaka = :oznaka
            ORDER BY t.teren_id;
        """,
        "parametri": {"oznaka": "J"},
    },
    "zgrade_i_javna_parkiralista_po_zonama": {
        "sql": """
            SELECT
                zk.naziv AS zona,
                COUNT(DISTINCT z.zgrada_id) AS broj_zgrada,
                COUNT(DISTINCT p.parkiraliste_id) AS broj_javnih_parkiralista
            FROM zone_kampusa AS zk
            JOIN zgrade AS z ON zk.zona_id = z.zona_id
            JOIN parkiralista AS p ON zk.zona_id = p.zona_id
            WHERE p.tip = :tip
            GROUP BY zk.zona_id, zk.naziv
            ORDER BY zk.naziv;
        """,
        "parametri": {"tip": "javno"},
    },
}


def izvrsi_upit(naziv_upita: str) -> pd.DataFrame:
    """Izvrsi izabrani upit i vrati rezultat kao DataFrame."""

    if naziv_upita not in SQL_UPITI:
        raise ValueError(f"Upit '{naziv_upita}' ne postoji.")

    podesavanja = ucitaj_podesavanja_baze()
    adresa_baze = URL.create(
        drivername="postgresql+psycopg2",
        username=podesavanja.korisnik,
        password=podesavanja.lozinka,
        host=podesavanja.host,
        port=podesavanja.port,
        database=podesavanja.naziv_baze,
    )
    engine = create_engine(adresa_baze)
    izabrani_upit = SQL_UPITI[naziv_upita]

    try:
        with engine.connect() as konekcija:
            return pd.read_sql_query(
                text(izabrani_upit["sql"]),
                konekcija,
                params=izabrani_upit["parametri"],
            )
    finally:
        engine.dispose()


def izvrsi_sve_upite() -> dict[str, pd.DataFrame]:
    """Izvrsi svih sedam upita i vrati njihove DataFrame rezultate."""

    return {naziv: izvrsi_upit(naziv) for naziv in SQL_UPITI}
