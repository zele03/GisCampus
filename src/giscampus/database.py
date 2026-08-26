"""Povezivanje sa PostgreSQL/PostGIS bazom i njena pocetna priprema."""

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

-- Poznate zgrade koje se rucno evidentiraju u sistemu.
CREATE TABLE IF NOT EXISTS zgrade (
    zgrada_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    zona_id INTEGER NOT NULL REFERENCES zone_kampusa(zona_id) ON DELETE RESTRICT,
    naziv VARCHAR(120) NOT NULL,
    tip VARCHAR(60) NOT NULL,
    povrsina_m2 NUMERIC(12, 2) CHECK (povrsina_m2 > 0),
    geometrija geometry(Polygon, 32634)
);

-- Parking povrsine koje se posmatraju kao celine.
CREATE TABLE IF NOT EXISTS parkiralista (
    parkiraliste_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    zona_id INTEGER NOT NULL REFERENCES zone_kampusa(zona_id) ON DELETE RESTRICT,
    tip VARCHAR(20) NOT NULL CHECK (tip IN ('javno', 'privatno')),
    povrsina_m2 NUMERIC(12, 2) CHECK (povrsina_m2 > 0),
    geometrija geometry(Polygon, 32634)
);

-- Parkovi, livade, travnjaci i druge zelene povrsine.
CREATE TABLE IF NOT EXISTS zelene_povrsine (
    zelena_povrsina_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    zona_id INTEGER NOT NULL REFERENCES zone_kampusa(zona_id) ON DELETE RESTRICT,
    tip VARCHAR(60) NOT NULL,
    povrsina_m2 NUMERIC(12, 2) CHECK (povrsina_m2 > 0),
    geometrija geometry(Polygon, 32634)
);

-- Odabrani infrastrukturni objekti predstavljeni tackama.
CREATE TABLE IF NOT EXISTS infrastrukturni_objekti (
    infrastrukturni_objekat_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    zona_id INTEGER NOT NULL REFERENCES zone_kampusa(zona_id) ON DELETE RESTRICT,
    naziv VARCHAR(120) NOT NULL,
    stanje VARCHAR(30) NOT NULL,
    geometrija geometry(Point, 32634)
);

-- Sportski tereni u juznom delu kampusa.
CREATE TABLE IF NOT EXISTS tereni (
    teren_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    zona_id INTEGER NOT NULL REFERENCES zone_kampusa(zona_id) ON DELETE RESTRICT,
    naziv VARCHAR(120) NOT NULL,
    povrsina_m2 NUMERIC(12, 2) CHECK (povrsina_m2 > 0),
    geometrija geometry(Polygon, 32634)
);
"""

SQL_UNOS_PODATAKA = """
-- Zone kampusa unose se prve jer njihove kljuceve koriste ostale tabele.
INSERT INTO zone_kampusa (naziv, oznaka) VALUES
    ('Severna', 'S'),
    ('Juzna', 'J'),
    ('Istocna', 'I'),
    ('Zapadna', 'Z'),
    ('Centralna', 'C');

INSERT INTO zgrade (zona_id, naziv, tip) VALUES
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'S'), 'Tehnoloski fakultet', 'fakultet'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'S'), 'Poljoprivredni fakultet', 'fakultet'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'C'), 'Pravni fakultet', 'fakultet'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'C'), 'Filozofski fakultet', 'fakultet'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'C'), 'Fakultet tehnickih nauka', 'fakultet'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'J'), 'Prirodno-matematicki fakultet', 'fakultet'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'I'), 'Ekonomski fakultet', 'fakultet'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'J'), 'Visoka poslovna skola', 'visoka skola'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'Z'), 'Naucno-tehnoloski park', 'naucno-tehnoloski park'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'Z'), 'Studentski dom A', 'studentski dom'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'Z'), 'Studentski dom B', 'studentski dom'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'Z'), 'Veseli vrtic', 'vrtic'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'I'), 'Rektorat', 'rektorat'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'J'), 'Institut BioSens', 'institut');

INSERT INTO parkiralista (zona_id, tip) VALUES
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'S'), 'javno'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'S'), 'privatno'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'S'), 'privatno'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'I'), 'javno'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'I'), 'privatno'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'C'), 'javno'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'C'), 'privatno'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'Z'), 'javno'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'Z'), 'javno'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'Z'), 'privatno'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'Z'), 'privatno'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'J'), 'javno');

INSERT INTO zelene_povrsine (zona_id, tip) VALUES
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'Z'), 'park'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'S'), 'livada'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'I'), 'dvoriste 1'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'I'), 'dvoriste 2'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'I'), 'dvoriste 3');

INSERT INTO infrastrukturni_objekti (zona_id, naziv, stanje) VALUES
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'I'), 'Trafostanica 1', 'dobro'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'I'), 'Trafostanica 2', 'dobro'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'I'), 'Fontana', 'neispravno'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'I'), 'Parkiraliste za bicikle', 'dobro'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'C'), 'Parkiraliste za bicikle', 'dobro'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'S'), 'Kontejner', 'dobro');

INSERT INTO tereni (zona_id, naziv) VALUES
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'J'), 'Teren za fudbal'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'J'), 'Teren za mali fudbal 1'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'J'), 'Teren za mali fudbal 2'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'J'), 'Teren za mali fudbal 3'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'J'), 'Teren za kosarku 1'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'J'), 'Teren za kosarku 2'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'J'), 'Teren za tenis'),
    ((SELECT zona_id FROM zone_kampusa WHERE oznaka = 'J'), 'Teren za odbojku');
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
    "tereni": (
        "teren_id",
        "zona_id",
        "naziv",
        "povrsina_m2",
        "geometrija",
    ),
}

OCEKIVANI_BROJ_REDOVA = {
    "zone_kampusa": 5,
    "zgrade": 14,
    "parkiralista": 12,
    "zelene_povrsine": 5,
    "infrastrukturni_objekti": 6,
    "tereni": 8,
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
    """Kreiraj projektnu bazu ako ona vec ne postoji."""

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
    """Ukljuci PostGIS ekstenziju u projektnoj bazi i vrati njenu verziju."""

    with closing(povezi_se()) as konekcija:
        with konekcija.cursor() as kursor:
            kursor.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
            kursor.execute("SELECT PostGIS_Lib_Version();")
            verzija_postgis = kursor.fetchone()[0]

        konekcija.commit()

    return verzija_postgis


def kreiraj_tabele() -> tuple[str, ...]:
    """Kreiraj sest osnovnih tabela i vrati njihove nazive iz baze."""

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
    """Proveri kolone i opcione geometrije u svih sest tabela."""

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
                    f"Tabela '{naziv_tabele}' nema ocekivane kolone. "
                    f"Postojece: {postojece_kolone}. "
                    f"Ocekivane: {ocekivane_kolone}."
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


def prebroj_redove() -> dict[str, int]:
    """Vrati trenutni broj redova u svakoj projektnoj tabeli."""

    broj_redova = {}

    with closing(povezi_se()) as konekcija, konekcija.cursor() as kursor:
        for naziv_tabele in OCEKIVANI_BROJ_REDOVA:
            upit = sql.SQL("SELECT COUNT(*) FROM {};").format(
                sql.Identifier(naziv_tabele)
            )
            kursor.execute(upit)
            broj_redova[naziv_tabele] = kursor.fetchone()[0]

    return broj_redova


def unesi_pocetne_podatke() -> bool:
    """Rucno unesi dogovorene redove ako su sve projektne tabele prazne."""

    broj_redova = prebroj_redove()

    if broj_redova == OCEKIVANI_BROJ_REDOVA:
        return False

    if any(broj_redova.values()):
        raise RuntimeError(
            "Pocetni podaci nisu uneti jer neke tabele vec sadrze redove. "
            f"Trenutno stanje: {broj_redova}."
        )

    with closing(povezi_se()) as konekcija:
        with konekcija.cursor() as kursor:
            kursor.execute(SQL_UNOS_PODATAKA)

        konekcija.commit()

    broj_redova = prebroj_redove()
    if broj_redova != OCEKIVANI_BROJ_REDOVA:
        raise RuntimeError(
            f"Broj unetih redova ne odgovara planu. Trenutno stanje: {broj_redova}."
        )

    return True


if __name__ == "__main__":
    naziv_projektne_baze = ucitaj_podesavanja_baze().naziv_baze
    verzija_postgresql, verzija_postgis = proveri_konekciju()
    print("Konekcija sa PostgreSQL serverom je uspesna.")
    print(f"PostgreSQL: {verzija_postgresql}")
    print(f"Dostupna PostGIS verzija: {verzija_postgis or 'nije pronadjena'}")

    baza_je_kreirana = kreiraj_bazu()
    if baza_je_kreirana:
        print(f"Baza '{naziv_projektne_baze}' je uspesno kreirana.")
    else:
        print(f"Baza '{naziv_projektne_baze}' vec postoji.")

    aktivna_verzija_postgis = ukljuci_postgis()
    print(f"PostGIS je ukljucen u projektnoj bazi: {aktivna_verzija_postgis}")

    tabele = kreiraj_tabele()
    if set(tabele) != set(OCEKIVANE_KOLONE):
        raise RuntimeError(
            f"Baza sadrzi neocekivane projektne tabele. Postojece tabele: {tabele}"
        )

    proveri_strukturu_tabela()
    print("Projektne tabele su uspesno kreirane:")
    for tabela in tabele:
        print(f"- {tabela}")
    print("Struktura svih sest tabela je uspesno proverena.")

    podaci_su_uneti = unesi_pocetne_podatke()
    if podaci_su_uneti:
        print("Pocetni podaci su uspesno uneti rucnim INSERT naredbama.")
    else:
        print("Pocetni podaci vec postoje i nisu ponovo unoseni.")

    print("Broj redova u projektnim tabelama:")
    for tabela, broj_redova in prebroj_redove().items():
        print(f"- {tabela}: {broj_redova}")
