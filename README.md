# GisCampus

Studentski projekat iz predmeta **Osnove geoinformatike**. Aplikacija objedinjuje PostgreSQL/PostGIS bazu, prostorne podatke, interaktivnu mapu i ML segmentaciju zgrada za univerzitetski kampus u Novom Sadu.

## Šta projekat sadrži

- sedam PostGIS tabela sa atributima i geometrijama;
- CRUD operacije i SQL JOIN/WHERE upite;
- ručno evidentirane zone, zgrade, parkirališta, zelene površine, infrastrukturne objekte i terene;
- raster kampusa i devet prostornih analiza;
- već istrenirani U-Net sa ResNet34 enkoderom za izdvajanje zgrada;
- Streamlit aplikaciju sa Folium/Leaflet mapom;
- rezervnu kopiju trenutne baze za prenos na drugi računar.

## Preduslovi

Projekat je proveren sa Windows 10/11, Python 3.12, PostgreSQL 17 i PostGIS 3.6. PostgreSQL instalacija mora sadržati alate `pg_dump` i `pg_restore`. Za preuzimanje rastera i težina modela potrebna je internet veza.

## Postavljanje na novom računaru

### 1. Preuzimanje projekta

```powershell
git clone <URL_REPOZITORIJUMA>
cd GisCampus
```

### 2. Python okruženje

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

`requirements.txt` sadrži verzije biblioteka iz proverenog okruženja.

### 3. Podešavanje baze

```powershell
Copy-Item .env.example .env
```

U `.env` zatim treba upisati podatke lokalnog PostgreSQL servera:

```text
DB_HOST=localhost
DB_PORT=5432
DB_NAME=gis_kampus
DB_USER=postgres
DB_PASSWORD=vaša_lozinka
```

`.env` sadrži lozinku i zato se ne postavlja na GitHub.

### 4. Obnavljanje projektne baze

Repozitorijum sadrži `data/backup/gis_kampus.backup` sa sedam tabela, ključevima, geometrijama, ML rezultatima i statusima provere. Obnavljanje zamenjuje projektne tabele u bazi navedenoj u `.env`, pa zahteva izričitu potvrdu:

```powershell
.\scripts\restore_database.ps1 -Force
```

Skripta prvo pravi bazu i uključuje PostGIS ako je potrebno, a zatim obnavlja projektne tabele. Odbija rad nad sistemskim bazama `postgres`, `template0` i `template1`.

Za praznu početnu evidenciju bez sačuvanih geometrija i ML statusa umesto restore skripte može se pokrenuti:

```powershell
python -m src.giscampus.sql.database
```

### 5. Preuzimanje rasterske podloge

Raster je veliki lokalni fajl i nije u Git repozitorijumu. Ova komanda preuzima Esri World Imagery raster za definisani okvir kampusa:

```powershell
python scripts/prepare_assets.py
```

Za ponovno pokretanje ML detekcije mogu se preuzeti i težine modela:

```powershell
python scripts/prepare_assets.py --with-model
```

Model dolazi iz repozitorijuma [nilsho01/unet-resnet34-vhr-buildings](https://huggingface.co/nilsho01/unet-resnet34-vhr-buildings). Mali ručno nacrtani GeoJSON fajlovi čuvaju se u `data/processed/campus/`.

### 6. Provera okruženja

```powershell
python scripts/check_setup.py
```

Provera prikazuje Python verziju, postojanje `.env` fajla, rastera, backupa i ML fajlova, PostGIS verziju i broj redova u svakoj tabeli. Nedostajući ML rasteri nisu prepreka za običan rad aplikacije ako su ML poligoni već obnovljeni iz baze.

### 7. Pokretanje aplikacije

```powershell
python -m streamlit run app.py
```

Streamlit prikazuje lokalnu adresu, najčešće `http://localhost:8501`.

## Rezervna kopija posle izmena

Nakon promene podataka, geometrija ili ML statusa napraviti novu kopiju:

```powershell
.\scripts\backup_database.ps1 -Force
```

Skripta čuva samo sedam projektnih tabela u `data/backup/gis_kampus.backup`. Lozinka iz `.env` ne upisuje se u backup.

## Ponovno pokretanje ML obrade

Ovi koraci nisu potrebni za običan pregled obnovljene baze:

```powershell
python scripts/prepare_assets.py --with-model
python -m src.giscampus.ml.detection
python -m src.giscampus.ml.vectorization
```

Detekcija pravi raster verovatnoće, binarnu masku i PNG pregled. Vektorizacija pravi `ml_zgrade.geojson`. Upis se podrazumevano preskače ako ML tabela već ima redove, a ručno promenjeni statusi dodatno su zaštićeni od zamene.

## Testovi

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

## Važne napomene

- `restore_database.ps1 -Force` zamenjuje projektne tabele sadržajem backupa.
- Backup treba osvežiti nakon važnih promena baze.
- Geofabrik `latest` i URL modela sa granom `main` mogu kasnije dati novije podatke ili težine.
- Aplikacija je lokalni studentski projekat, ne javni višekorisnički servis.
- Za potpuno offline pokretanje unapred treba sačuvati raster, model i veb resurse mape.

## Organizacija projekta

```text
GisCampus/
|-- app.py
|-- requirements.txt
|-- scripts/
|   |-- backup_database.ps1
|   |-- restore_database.ps1
|   |-- check_setup.py
|   `-- prepare_assets.py
|-- src/giscampus/
|   |-- sql/          # baza, CRUD i SQL upiti
|   |-- geo/          # podaci, povezivanje, mapa i analize
|   `-- ml/           # model, detekcija, prikaz i vektorizacija
|-- data/
|   |-- backup/       # kopija projektnih tabela
|   |-- processed/    # mali ručno pripremljeni GeoJSON fajlovi
|   |-- raw/          # veliki lokalni SHP i raster podaci
|   `-- ml/           # težine i ML izlazi
|-- docs/             # MD i PDF dokumentacija
`-- tests/
```
