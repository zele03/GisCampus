"""Provera da li lokalno okruženje sadrži sve potrebno za GisCampus."""

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

KOREN = Path(__file__).resolve().parents[1]
if str(KOREN) not in sys.path:
    sys.path.insert(0, str(KOREN))

OBAVEZNI_FAJLOVI = {
    "rasterska podloga": KOREN / "data/raw/raster/kampus_esri.tif",
    "rezervna kopija baze": KOREN / "data/backup/gis_kampus.backup",
}
ML_FAJLOVI = {
    "težine modela": KOREN / "data/ml/models/unet_bldg_instance.pth",
    "raster verovatnoće": KOREN / "data/ml/results/verovatnoca_zgrada.tif",
    "binarna maska": KOREN / "data/ml/results/maska_zgrada.tif",
    "ML GeoJSON": KOREN / "data/ml/results/ml_zgrade.geojson",
}


def oznaka(uspeh: bool) -> str:
    return "[OK]" if uspeh else "[NEDOSTAJE]"


def main() -> int:
    greske = []
    upozorenja = []
    print(f"Python: {sys.version.split()[0]}")
    if sys.version_info[:2] != (3, 12):
        upozorenja.append("Preporučena verzija je Python 3.12.")

    env = KOREN / ".env"
    env_ok = env.exists() and "unesite_lozinku" not in env.read_text(encoding="utf-8")
    print(f"{oznaka(env_ok)} .env")
    if not env_ok:
        greske.append("Napravite i popunite .env prema .env.example fajlu.")

    for naziv, putanja in OBAVEZNI_FAJLOVI.items():
        postoji = putanja.exists() and putanja.stat().st_size > 0
        print(f"{oznaka(postoji)} {naziv}: {putanja.relative_to(KOREN)}")
        if not postoji:
            greske.append(f"Nedostaje {naziv}: {putanja.relative_to(KOREN)}")

    for naziv, putanja in ML_FAJLOVI.items():
        postoji = putanja.exists() and putanja.stat().st_size > 0
        print(f"{'[OK]' if postoji else '[OPCIONO]'} {naziv}: {putanja.relative_to(KOREN)}")
        if not postoji:
            upozorenja.append(f"{naziv} je potreban za ponovno pokretanje ili pregled ML rezultata.")

    if env_ok:
        try:
            from src.giscampus.sql.database import PROJEKTNE_TABELE, povezi_se

            with povezi_se() as konekcija, konekcija.cursor() as kursor:
                kursor.execute("SELECT PostGIS_Lib_Version();")
                print(f"[OK] PostGIS {kursor.fetchone()[0]}")
                for tabela in PROJEKTNE_TABELE:
                    kursor.execute(f'SELECT COUNT(*) FROM "{tabela}";')
                    print(f"[OK] {tabela}: {kursor.fetchone()[0]} redova")
        except Exception as exc:  # noqa: BLE001
            greske.append(f"Baza nije spremna: {exc}")

    for poruka in upozorenja:
        print(f"UPOZORENJE: {poruka}")
    if greske:
        for poruka in greske:
            print(f"GREŠKA: {poruka}")
        return 1

    print("Okruženje je spremno za pokretanje aplikacije.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
