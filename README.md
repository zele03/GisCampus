# GisCampus

Studentski projekat iz predmeta **Osnove geoinformatike**.

GisCampus je GIS aplikacija za upravljanje infrastrukturom univerzitetskog
kampusa. Projekat ce objediniti PostgreSQL/PostGIS bazu, obradu prostornih
podataka u Pythonu i automatsko izdvajanje zgrada sa ortofoto snimaka pomocu
masinskog ucenja.

## Planirane celine

1. PostgreSQL/PostGIS baza i CRUD operacije iz Pythona
2. Ucitavanje, povezivanje i analiza vektorskih i rasterskih podataka
3. ML izdvajanje zgrada i cuvanje rezultata u PostGIS bazi
4. Interaktivni GIS interfejs

## Trenutni status

Postavljeno je lokalno Python 3.12 virtuelno okruzenje i kompletna pocetna
struktura projekta. Ostvarena je konekcija sa PostgreSQL serverom i pripremljeno
je automatsko kreiranje projektne baze `gis_kampus` sa PostGIS ekstenzijom.
Definisano je sest povezanih tabela za zone, zgrade, parkiralista, zelene
povrsine, infrastrukturne objekte i sportske terene. Pripremljen je rucni unos
pocetnih podataka SQL `INSERT` naredbama, sa najmanje pet redova u svakoj
tabeli. Podaci iz svih sest tabela ucitavaju se u zasebne pandas DataFrame
objekte. Obezbedjene su opste CRUD operacije za prikaz, dodavanje, azuriranje i
brisanje redova u svih sest tabela. Dodato je sedam SQL upita koji povezuju dve
ili tri tabele pomocu `JOIN` i filtriraju podatke pomocu `WHERE`. Povrsine i
geometrije bice dopunjene u GEO delu projekta.

## Lokalno pokretanje

U PowerShell terminalu aktivirati virtuelno okruzenje:

```powershell
.\.venv\Scripts\Activate.ps1
```

Proveriti aktivnu verziju Pythona:

```powershell
python --version
```

Ocekivana verzija je Python 3.12.

Instalirati trenutno potrebne biblioteke:

```powershell
python -m pip install -r requirements.txt
```

Proveriti konekciju i pripremiti projektnu bazu:

```powershell
python -m src.giscampus.sql.database
```

## Struktura

```text
GisCampus/
|-- app.py                         # Glavna aplikacija
|-- requirements.txt              # Python biblioteke
|-- src/giscampus/                 # Izvorni Python kod
|   |-- sql/                       # Baza, CRUD i SQL upiti
|   |-- spatial.py                 # Prostorni podaci i analize
|   |-- ml.py                      # Masinsko ucenje
|   `-- mapping.py                 # Prikaz podataka na mapi
|-- data/                          # Lokalni prostorni podaci i rezultati
|-- docs/                          # Projektna dokumentacija
|-- notebooks/                     # Zavrsna demonstraciona sveska
|-- tests/                         # Automatske provere
|-- .gitignore
`-- README.md
```
