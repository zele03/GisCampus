# GisCampus

Studentski projekat iz predmeta **Osnove geoinformatike**.

GisCampus je GIS aplikacija za upravljanje infrastrukturom univerzitetskog
kampusa. Projekat će objediniti PostgreSQL/PostGIS bazu, obradu prostornih
podataka u Pythonu i automatsko izdvajanje zgrada sa ortofoto snimaka pomoću
mašinskog učenja.

## Planirane celine

1. PostgreSQL/PostGIS baza i CRUD operacije iz Pythona
2. Učitavanje, povezivanje i analiza vektorskih i rasterskih podataka
3. ML izdvajanje zgrada i čuvanje rezultata u PostGIS bazi
4. Interaktivni GIS interfejs

## Trenutni status

Postavljeno je lokalno Python 3.12 virtuelno okruženje i kompletna početna
struktura projekta. Ostvarena je konekcija sa PostgreSQL serverom i pripremljeno
je automatsko kreiranje projektne baze `gis_kampus` sa PostGIS ekstenzijom i
pet povezanih prostornih tabela sa po pet kolona za kampus Univerziteta u Novom
Sadu. Podaci i CRUD operacije još nisu dodati.

## Lokalno pokretanje

U PowerShell terminalu aktivirati virtuelno okruženje:

```powershell
.\.venv\Scripts\Activate.ps1
```

Proveriti aktivnu verziju Pythona:

```powershell
python --version
```

Očekivana verzija je Python 3.12.

Instalirati trenutno potrebne biblioteke:

```powershell
python -m pip install -r requirements.txt
```

Proveriti konekciju i pripremiti projektnu bazu:

```powershell
python -m src.giscampus.database
```

## Struktura

```text
GisCampus/
|-- app.py                         # Glavna aplikacija
|-- requirements.txt              # Python biblioteke
|-- src/giscampus/                 # Izvorni Python kod
|-- data/                          # Lokalni prostorni podaci i rezultati
|-- docs/                          # Projektna dokumentacija
|-- notebooks/                     # Završna demonstraciona sveska
|-- tests/                         # Automatske provere
|-- .gitignore
`-- README.md
```
