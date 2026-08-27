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

Za GEO deo koristi se Geofabrik SHP paket sa OpenStreetMap podacima za Srbiju.
Originalna arhiva i raspakovani slojevi cuvaju se lokalno u
`data/raw/vector/` i ne postavljaju se na GitHub. Pet relevantnih SHP slojeva
ucitava se pomocu GeoPandas biblioteke samo za okvir kampusa, a njihove
informacije se zatim pretvaraju u zasebne pandas DataFrame objekte uz zadrzanu
kolonu `geometry`.

Preuzet je Esri World Imagery raster za tacan okvir kampusa i sacuvan kao
georeferencirani TIFF u `data/raw/raster/`. Pripremljena je interaktivna HTML
mapa za proveru OSM poligona svih evidentiranih zgrada. Zgrade mogu imati
`MultiPolygon` geometriju, studentski domovi nose stvarne nazive, a za Rektorat
je izabrana samo centralna zgrada. OSM poligoni su povezani sa 14 redova tabele
`zgrade` preko pomocnog Python mapiranja naziva i `osm_id` vrednosti. Geometrije
su upisane u PostGIS u EPSG:32634, zajedno sa izracunatim povrsinama.

Dodat je prvi interaktivni ekran aplikacije za rucno crtanje okvira celog
kampusa i pet zona preko rastera. Rucno nacrtane zone su prostorno ociscene:
odseceni su delovi van okvira, uklonjena su preklapanja i popunjene su male
praznine. Konacni rezultat je sacuvan u
`data/processed/campus/zone.geojson`, dok je prvobitni crtez uklonjen.
Ocisceni poligoni su povezani sa pet postojecih redova tabele `zone_kampusa` i
upisani u PostGIS u EPSG:32634, zajedno sa izracunatim povrsinama.
Strani kljucevi zgrada provereni su u odnosu na nacrtane zone; FTN ostaje u
Centralnoj, a Ekonomski fakultet pripada Zapadnoj zoni.

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

Napraviti interaktivnu mapu za proveru zgrada:

```powershell
python -m src.giscampus.geo.map
```

Mapa se zatim otvara iz `data/outputs/provera_zgrada.html`.

Pokrenuti interaktivnu aplikaciju za crtanje zona:

```powershell
python -m streamlit run app.py
```

## Struktura

```text
GisCampus/
|-- app.py                         # Glavna aplikacija
|-- requirements.txt              # Python biblioteke
|-- src/giscampus/                 # Izvorni Python kod
|   |-- sql/                       # Baza, CRUD i SQL upiti
|   |-- geo/                       # Prostorni podaci, analize i mapa
|   |   |-- data.py               # Ucitavanje i spajanje podataka
|   |   |-- analysis.py           # Overlay i prostorni upiti
|   |   `-- map.py                # Slojevi, simbologija i raster
|   `-- ml.py                      # Masinsko ucenje
|-- data/                          # Lokalni prostorni podaci i rezultati
|-- docs/                          # Projektna dokumentacija
|-- notebooks/                     # Zavrsna demonstraciona sveska
|-- tests/                         # Automatske provere
|-- .gitignore
`-- README.md
```
