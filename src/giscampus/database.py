"""Povezivanje sa PostgreSQL/PostGIS bazom i njena početna priprema."""

from contextlib import closing

from psycopg2 import connect, sql

from .config import ucitaj_podesavanja_baze


SQL_KREIRANJE_TABELA = """
-- Prostorne zone kampusa Univerziteta u Novom Sadu.
CREATE TABLE IF NOT EXISTS zone_kampusa (
    zona_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    naziv VARCHAR(50) NOT NULL UNIQUE,
    oznaka VARCHAR(5) NOT NULL UNIQUE,
    povrsina_m2 NUMERIC(12, 2) CHECK (povrsina_m2 > 0),
    geometrija geometry(Polygon, 32634)
);

-- Poznate zgrade koje se ručno evidentiraju u sistemu.
CREATE TABLE IF NOT EXISTS zgrade (
    zgrada_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    zona_id INTEGER NOT NULL REFERENCES zone_kampusa(zona_id) ON DELETE RESTRICT,
    naziv VARCHAR(120) NOT NULL,
    tip VARCHAR(60) NOT NULL,
    povrsina_m2 NUMERIC(12, 2) CHECK (povrsina_m2 > 0),
    geometrija geometry(Polygon, 32634)
);

-- Parking površine koje se posmatraju kao celine.
CREATE TABLE IF NOT EXISTS parkiralista (
    parkiraliste_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    zona_id INTEGER NOT NULL REFERENCES zone_kampusa(zona_id) ON DELETE RESTRICT,
    tip VARCHAR(20) NOT NULL CHECK (tip IN ('javno', 'privatno')),
    povrsina_m2 NUMERIC(12, 2) CHECK (povrsina_m2 > 0),
    geometrija geometry(Polygon, 32634)
);

-- Parkovi, livade, travnjaci i druge zelene površine.
CREATE TABLE IF NOT EXISTS zelene_povrsine (
    zelena_povrsina_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    zona_id INTEGER NOT NULL REFERENCES zone_kampusa(zona_id) ON DELETE RESTRICT,
    tip VARCHAR(60) NOT NULL,
    povrsina_m2 NUMERIC(12, 2) CHECK (povrsina_m2 > 0),
    geometrija geometry(Polygon, 32634)
);

-- Odabrani infrastrukturni objekti predstavljeni tačkama.
CREATE TABLE IF NOT EXISTS infrastrukturni_objekti (
    infrastrukturni_objekat_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    zona_id INTEGER NOT NULL REFERENCES zone_kampusa(zona_id) ON DELETE RESTRICT,
    naziv VARCHAR(120) NOT NULL,
    stanje VARCHAR(30) NOT NULL,
    geometrija geometry(Point, 32634)
);
"""

OCEKIVANE_KOLONE = {
    "zone_kampusa": ("zona_id", "naziv", "oznaka", "povrsina_m2", "geometrija"),
    "zgrade": (
        "zgrada_id",
        "zona_id",
        "naziv",
        "tip",
        "povrsina_m2",
        "geometrija",
    ),
    "parkiralista": (
        "parkiraliste_id",
        "zona_id",
        "tip",
        "povrsina_m2",
        "geometrija",
    ),
    "zelene_povrsine": (
        "zelena_povrsina_id",
        "zona_id",
        "tip",
        "povrsina_m2",
        "geometrija",
    ),
    "infrastrukturni_objekti": (
        "infrastrukturni_objekat_id",
        "zona_id",
        "naziv",
        "stanje",
        "geometrija",
    ),
}


def povezi_se(naziv_baze: str | None = None):
    """Otvori konekciju ka zadatoj ili projektnoj PostgreSQL bazi."""

    podesavanja = ucitaj_podesavanja_baze()

    return connect(
        host=podesavanja.host,
        port=podesavanja.port,
        dbname=naziv_baze or podesavanja.naziv_baze,
        user=podesavanja.korisnik,
        password=podesavanja.lozinka,
    )


def proveri_konekciju() -> tuple[str, str | None]:
    """Proveri pristup serveru i dostupnost PostGIS ekstenzije."""

    with (
        closing(povezi_se("postgres")) as konekcija,
        konekcija.cursor() as kursor,
    ):
        kursor.execute("SELECT version();")
        verzija_postgresql = kursor.fetchone()[0]

        kursor.execute(
            """
            SELECT default_version
            FROM pg_available_extensions
            WHERE name = 'postgis';
            """
        )
        red = kursor.fetchone()
        verzija_postgis = red[0] if red else None

    return verzija_postgresql, verzija_postgis


def kreiraj_bazu() -> bool:
    """Kreiraj projektnu bazu ako ona već ne postoji."""

    podesavanja = ucitaj_podesavanja_baze()

    with closing(povezi_se("postgres")) as konekcija:
        konekcija.autocommit = True

        with konekcija.cursor() as kursor:
            kursor.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s;",
                (podesavanja.naziv_baze,),
            )

            if kursor.fetchone():
                return False

            upit = sql.SQL("CREATE DATABASE {};").format(
                sql.Identifier(podesavanja.naziv_baze)
            )
            kursor.execute(upit)

    return True


def ukljuci_postgis() -> str:
    """Uključi PostGIS ekstenziju u projektnoj bazi i vrati njenu verziju."""

    with closing(povezi_se()) as konekcija:
        with konekcija.cursor() as kursor:
            kursor.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
            kursor.execute("SELECT PostGIS_Lib_Version();")
            verzija_postgis = kursor.fetchone()[0]

        konekcija.commit()

    return verzija_postgis


def kreiraj_tabele() -> tuple[str, ...]:
    """Kreiraj pet osnovnih tabela i vrati njihove nazive iz baze."""

    with closing(povezi_se()) as konekcija:
        with konekcija.cursor() as kursor:
            kursor.execute(SQL_KREIRANJE_TABELA)
            kursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_type = 'BASE TABLE'
                  AND table_name <> 'spatial_ref_sys'
                ORDER BY table_name;
                """
            )
            tabele = tuple(red[0] for red in kursor.fetchall())

        konekcija.commit()

    return tabele


def proveri_strukturu_tabela() -> None:
    """Proveri kolone i opcione geometrije u svih pet tabela."""

    with closing(povezi_se()) as konekcija, konekcija.cursor() as kursor:
        for naziv_tabele, ocekivane_kolone in OCEKIVANE_KOLONE.items():
            kursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position;
                """,
                (naziv_tabele,),
            )
            postojece_kolone = tuple(red[0] for red in kursor.fetchall())

            if postojece_kolone != ocekivane_kolone:
                raise RuntimeError(
                    f"Tabela '{naziv_tabele}' nema očekivane kolone. "
                    f"Postojeće: {postojece_kolone}. "
                    f"Očekivane: {ocekivane_kolone}."
                )

            kursor.execute(
                """
                SELECT is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = %s
                  AND column_name = 'geometrija';
                """,
                (naziv_tabele,),
            )

            if kursor.fetchone() != ("YES",):
                raise RuntimeError(
                    f"Geometrija u tabeli '{naziv_tabele}' mora dozvoliti NULL."
                )


if __name__ == "__main__":
    naziv_projektne_baze = ucitaj_podesavanja_baze().naziv_baze
    verzija_postgresql, verzija_postgis = proveri_konekciju()
    print("Konekcija sa PostgreSQL serverom je uspešna.")
    print(f"PostgreSQL: {verzija_postgresql}")
    print(f"Dostupna PostGIS verzija: {verzija_postgis or 'nije pronađena'}")

    baza_je_kreirana = kreiraj_bazu()
    if baza_je_kreirana:
        print(f"Baza '{naziv_projektne_baze}' je uspešno kreirana.")
    else:
        print(f"Baza '{naziv_projektne_baze}' već postoji.")

    aktivna_verzija_postgis = ukljuci_postgis()
    print(f"PostGIS je uključen u projektnoj bazi: {aktivna_verzija_postgis}")

    tabele = kreiraj_tabele()
    if set(tabele) != set(OCEKIVANE_KOLONE):
        raise RuntimeError(
            "Baza sadrži neočekivane projektne tabele. "
            f"Postojeće tabele: {tabele}"
        )

    proveri_strukturu_tabela()
    print("Projektne tabele su uspešno kreirane:")
    for tabela in tabele:
        print(f"- {tabela}")
    print("Struktura svih pet tabela je uspešno proverena.")
