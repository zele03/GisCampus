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
Tabela `parkiralista` dopunjena je jedinstvenom kolonom `naziv`, sa vrednostima
od `parkiraliste_1` do `parkiraliste_12`, radi jednostavnog povezivanja sa
rucno nacrtanim poligonima. Interaktivni ekran sada omogucava izbor jednog od
12 redova iz baze i cuvanje nacrtanog poligona u
`data/processed/campus/parkiralista.geojson`. Svih 12 poligona povezano je sa
tabelom `parkiralista` preko `parkiraliste_id` i naziva, a geometrije i
izracunate povrsine upisane su u PostGIS u EPSG:32634.
Interaktivni ekran je zatim prilagodjen za crtanje pet redova iz tabele
`zelene_povrsine`. Kao opcioni referentni sloj prikazuju se objekti klasa
`park`, `grass` i `forest` iz vec preuzetog SHP sloja namene zemljista, dok se
rucni crtezi cuvaju u `data/processed/campus/zelene_povrsine.geojson`. Svih pet
poligona povezano je sa tabelom `zelene_povrsine` preko primarnog kljuca i tipa,
a geometrije i izracunate povrsine upisane su u PostGIS u EPSG:32634.
Infrastrukturni objekti su rucno evidentirani kao tacke i sacuvani u
`data/processed/campus/infrastrukturni_objekti.geojson`. Svih sest tacaka
povezano je sa tabelom `infrastrukturni_objekti` preko primarnog kljuca i naziva,
a geometrije su upisane u PostGIS u EPSG:32634. Osam `pitch` poligona iz
Geofabrik SHP sloja rucno je upareno sa odgovarajucim terenima pre upisa u
PostGIS.

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

Pokrenuti zavrsnu GIS aplikaciju:

```powershell
python -m streamlit run app.py
```

Svih osam sportskih terena povezano je sa rucno proverenim OSM poligonima,
a njihove povrsine i geometrije upisane su u PostGIS.

U aplikaciji je omoguceno ukljucivanje i iskljucivanje svih prostornih slojeva,
kao i promena njihove boje, providnosti i debljine ivice.
Kontrole slojeva i simbologije nalaze se direktno na interaktivnoj mapi.
U bocnoj traci dostupne su CRUD operacije nad svih sest projektnih tabela.
Izbor reda u tabeli naglasava odgovarajuci objekat na mapi, a klik na objekat
na mapi naglasava njegov red kada je odgovarajuca tabela otvorena u prikazu.
Ukljuceni slojevi ostaju sacuvani tokom izbora objekata, a izbor se moze
obrisati i dugmetom koje se pojavljuje direktno na mapi.
Isti izbor slojeva koristi se u svim CRUD rezimima, ukljucujuci crtanje
novog objekta i promenu statusa ML zgrada.
Dodavanje novog objekta zahteva sve atribute i rucno crtanje geometrije na
mapi. Za poligone se povrsina automatski racuna u EPSG:32634 pre upisa u bazu.
Za sve objekte osim same zone strani kljuc `zona_id` automatski se odredjuje
prema zoni koja potpuno sadrzi nacrtanu geometriju.
Dodato je sedam prostornih analiza: clip zgrada u Severnoj zoni, intersection
parkiralista i zelenila, njihova union operacija, difference kampusa i zgrada,
buffer infrastrukture, within infrastrukture u Centralnoj zoni i overlaps
parkinga i zgrada. Rezultat se prikazuje kao sloj i kao DataFrame.
Dodate su i dve analize ML rezultata: within izdvaja cele ML zgrade u
Severnoj zoni prema geometriji, a intersection prikazuje zajednicke povrsine
ML i evidentiranih zgrada, uz ID-eve, naziv evidentirane zgrade i povrsinu
preseka u m2. Obe analize koriste sve ML statuse i ne menjaju izvorne tabele.
Nepoklapanje sa evidentiranim zgradama nije automatski greska modela jer
rucna evidencija ne obuhvata sve zgrade kampusa.
Pripremljena je struktura ML dela i dodat je U-Net model za segmentaciju
zgrada. Koristi se vec istrenirani U-Net sa ResNet34 enkoderom i dodatnim
izlazima za granice i rastojanje, bez naseg ponovnog treniranja. Slede priprema
snimka, provera maske i pretvaranje rezultata u vektorske poligone.

Istrenirane tezine preuzimaju se sa modela
[nilsho01/unet-resnet34-vhr-buildings](https://huggingface.co/nilsho01/unet-resnet34-vhr-buildings),
koji je objavljen pod licencom AGPL-3.0. Model je treniran na skupu
hotosm/vhr-building-segmentation sa RGB ortofoto snimcima i OSM oznakama
zgrada. U projektu se koristi checkpoint unet_bldg_instance.pth; sam fajl
tezina se cuva u data/ml/models/ i ne postavlja se na GitHub.

Detekcija zgrada na rasteru kampusa pokrece se komandom:

```powershell
python -m src.giscampus.ml.detection
```

Raster se obradjuje preklopljenim iseccima velicine 256 x 256 piksela. Rezultat
se cuva u data/ml/results/ kao raster verovatnoce, georeferencirana binarna
maska i PNG pregled originalnog snimka sa oznacenim detekcijama. Detekcije van
poligona zona kampusa uklanjaju se iz svih izlaznih rezultata.

Binarna maska se zatim pretvara u vektorske poligone. Poligoni manji od 20 m2
uklanjaju se kao sum i dobijaju povrsinu, prosecnu pouzdanost i pocetni status
provere. Ako poligon prelazi granicu zona, ostaje jedan ceo objekat i dodeljuje
mu se zona u kojoj se nalazi najveci deo njegove povrsine. Poligoni se upisuju u
PostGIS tabelu ml_zgrade i ucitavaju u GeoDataFrame i pandas DataFrame.
U aplikaciji su prikazani kao poseban sloj ML zgrade. Za njih nisu dozvoljeni
rucni unos i brisanje; kroz aplikaciju se menja samo status provere na
nije_potvrdjeno, potvrdjeno ili odbijeno.
Pri izboru reda za promenu statusa ML zgrada se odmah naglasava na mapi
ako je njen sloj ukljucen, bez cekanja na cuvanje statusa.

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
|   `-- ml/                        # Detekcija zgrada masinskim ucenjem
|       |-- data.py                # Priprema snimaka i maski
|       |-- model.py               # U-Net model
|       |-- detection.py           # Pokretanje detekcije
|       |-- vectorization.py       # Maska u vektorske poligone
|       `-- visualization.py       # Vizuelna provera rezultata
|-- data/                          # Lokalni prostorni podaci i rezultati
|   `-- ml/                        # Snimci, maske, modeli i ML rezultati
|-- docs/                          # Projektna dokumentacija
|-- notebooks/                     # Zavrsna demonstraciona sveska
|-- tests/                         # Automatske provere
|-- .gitignore
`-- README.md
```
