"""Interaktivna aplikacija GisCampus za pregled i rucno crtanje slojeva."""

from pathlib import Path

import folium
import geopandas as gpd
import pandas as pd
import streamlit as st
from folium.features import DivIcon
from folium.plugins import Draw
from shapely.geometry import shape
from streamlit_folium import st_folium

from src.giscampus.geo.analysis import (
    PUTANJA_INFRASTRUKTURNIH_OBJEKATA,
    PUTANJA_PARKIRALISTA,
    PUTANJA_ZELENIH_POVRSINA,
    PUTANJA_ZONA,
)
from src.giscampus.geo.data import (
    OKVIR_KAMPUSA,
    preuzmi_raster_kampusa,
    ucitaj_shp_sloj,
)
from src.giscampus.geo.map import _dodaj_raster
from src.giscampus.sql.database import povezi_se

st.set_page_config(page_title="GisCampus", layout="wide")

SLOJEVI_ZA_CRTANJE = {
    "Parkiralista": {
        "id_kolona": "parkiraliste_id",
        "geometrija": "Polygon",
        "putanja": PUTANJA_PARKIRALISTA,
        "upit": """
            SELECT p.parkiraliste_id, p.naziv, p.zona_id,
                   z.naziv AS zona, p.tip
            FROM parkiralista p
            JOIN zone_kampusa z ON z.zona_id = p.zona_id
            ORDER BY p.parkiraliste_id;
        """,
    },
    "Zelene povrsine": {
        "id_kolona": "zelena_povrsina_id",
        "geometrija": "Polygon",
        "putanja": PUTANJA_ZELENIH_POVRSINA,
        "upit": """
            SELECT zp.zelena_povrsina_id, zp.zona_id,
                   z.naziv AS zona, zp.tip
            FROM zelene_povrsine zp
            JOIN zone_kampusa z ON z.zona_id = zp.zona_id
            ORDER BY zp.zelena_povrsina_id;
        """,
    },
    "Infrastrukturni objekti": {
        "id_kolona": "infrastrukturni_objekat_id",
        "geometrija": "Point",
        "putanja": PUTANJA_INFRASTRUKTURNIH_OBJEKATA,
        "upit": """
            SELECT io.infrastrukturni_objekat_id, io.naziv, io.zona_id,
                   z.naziv AS zona, io.stanje
            FROM infrastrukturni_objekti io
            JOIN zone_kampusa z ON z.zona_id = io.zona_id
            ORDER BY io.infrastrukturni_objekat_id;
        """,
    },
}

BOJE_SLOJEVA = {
    "Parkiralista": "#ff3b30",
    "Zelene povrsine": "#00a651",
    "Infrastrukturni objekti": "#ff9500",
}


@st.cache_data(ttl="5m", max_entries=10)
def ucitaj_redove_iz_baze(naziv_sloja: str) -> pd.DataFrame:
    """Ucitaj SQL redove izabranog sloja zajedno sa nazivom zone."""

    konfiguracija = SLOJEVI_ZA_CRTANJE[naziv_sloja]
    with povezi_se() as konekcija, konekcija.cursor() as kursor:
        kursor.execute(konfiguracija["upit"])
        redovi = kursor.fetchall()
        kolone = [opis.name for opis in kursor.description]

    return pd.DataFrame(redovi, columns=kolone)


def ucitaj_sacuvani_sloj(naziv_sloja: str) -> gpd.GeoDataFrame:
    """Ucitaj rucno sacuvani GeoJSON izabranog sloja."""

    konfiguracija = SLOJEVI_ZA_CRTANJE[naziv_sloja]
    putanja = konfiguracija["putanja"]
    if putanja.exists():
        return gpd.read_file(putanja)

    kolone = list(ucitaj_redove_iz_baze(naziv_sloja).columns)
    prazni_podaci = {kolona: [] for kolona in kolone}
    return gpd.GeoDataFrame(
        prazni_podaci,
        geometry=gpd.GeoSeries([], crs="EPSG:4326"),
    )


def proveri_pripadnost_zoni(geometrija, naziv_zone: str) -> None:
    """Proveri da li nacrtana geometrija pripada izabranoj zoni."""

    zone = gpd.read_file(PUTANJA_ZONA).to_crs(32634)
    zona = zone[zone["naziv"] == naziv_zone].geometry.iloc[0]
    geometrija_m = gpd.GeoSeries([geometrija], crs=4326).to_crs(32634).iloc[0]

    if geometrija_m.geom_type == "Point":
        if not zona.covers(geometrija_m):
            raise ValueError(f"Tacka mora biti unutar zone {naziv_zone}.")
        return

    procenat_u_zoni = geometrija_m.intersection(zona).area / geometrija_m.area
    if procenat_u_zoni < 0.9:
        raise ValueError(
            f"Poligon mora biti u zoni {naziv_zone}. Trenutno je samo "
            f"{procenat_u_zoni:.0%} njegove povrsine u toj zoni."
        )


def sacuvaj_geometriju(
    naziv_sloja: str,
    objekat_id: int,
    podaci: pd.Series,
    geojson_geometrija: dict,
) -> None:
    """Sacuvaj ili zameni geometriju izabranog SQL reda u GeoJSON fajlu."""

    konfiguracija = SLOJEVI_ZA_CRTANJE[naziv_sloja]
    geometrija = shape(geojson_geometrija)
    if geometrija.geom_type != konfiguracija["geometrija"]:
        raise ValueError(
            f"Za sloj {naziv_sloja} potrebna je geometrija "
            f"{konfiguracija['geometrija']}."
        )
    if not geometrija.is_valid:
        raise ValueError("Nacrtana geometrija nije ispravna.")

    proveri_pripadnost_zoni(geometrija, podaci["zona"])
    id_kolona = konfiguracija["id_kolona"]
    sacuvani = ucitaj_sacuvani_sloj(naziv_sloja)
    sacuvani = sacuvani[sacuvani[id_kolona] != objekat_id]

    vrednosti = podaci.to_dict()
    vrednosti[id_kolona] = objekat_id
    vrednosti["geometry"] = geometrija
    novi_red = gpd.GeoDataFrame(
        [vrednosti],
        geometry="geometry",
        crs="EPSG:4326",
    )
    sacuvani = gpd.GeoDataFrame(
        pd.concat([sacuvani, novi_red], ignore_index=True),
        geometry="geometry",
        crs="EPSG:4326",
    ).sort_values(id_kolona)

    putanja: Path = konfiguracija["putanja"]
    putanja.parent.mkdir(parents=True, exist_ok=True)
    sacuvani.to_file(putanja, driver="GeoJSON")


def dodaj_sacuvane_slojeve(mapa: folium.Map) -> None:
    """Dodaj sve do sada rucno sacuvane slojeve na mapu."""

    for naziv_sloja, konfiguracija in SLOJEVI_ZA_CRTANJE.items():
        putanja = konfiguracija["putanja"]
        if not putanja.exists():
            continue

        sloj = gpd.read_file(putanja)
        boja = BOJE_SLOJEVA[naziv_sloja]
        opcije = {
            "name": naziv_sloja,
            "tooltip": folium.GeoJsonTooltip(
                fields=[konfiguracija["id_kolona"], "zona"],
                aliases=["ID", "Zona"],
            ),
            "show": naziv_sloja == "Infrastrukturni objekti",
        }
        if konfiguracija["geometrija"] == "Polygon":
            opcije["style_function"] = lambda _, boja=boja: {
                "color": boja,
                "weight": 3,
                "fillColor": boja,
                "fillOpacity": 0.25,
            }

        folium.GeoJson(sloj, **opcije).add_to(mapa)


@st.cache_data(max_entries=1)
def ucitaj_geofabrik_terene() -> gpd.GeoDataFrame:
    """Izdvoji osam Geofabrik terena koji se nalaze u Juznoj zoni."""

    objekti = ucitaj_shp_sloj("poligonski_objekti")
    zone = gpd.read_file(PUTANJA_ZONA)
    juzna = zone[zone["naziv"] == "Juzna"].geometry.iloc[0]
    tereni = objekti[
        (objekti["fclass"] == "pitch") & objekti.geometry.intersects(juzna)
    ].copy()
    tereni_m = tereni.to_crs(32634)
    tereni["povrsina_m2"] = tereni_m.geometry.area.round(2).to_numpy()
    return tereni


def dodaj_geofabrik_terene(mapa: folium.Map) -> None:
    """Dodaj poligone terena i vidljive OSM ID oznake na mapu."""

    tereni = ucitaj_geofabrik_terene()
    folium.GeoJson(
        tereni,
        name="Geofabrik tereni",
        style_function=lambda _: {
            "color": "#ffd60a",
            "weight": 4,
            "fillColor": "#ffd60a",
            "fillOpacity": 0.25,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["osm_id", "povrsina_m2"],
            aliases=["OSM ID", "Povrsina m2"],
        ),
    ).add_to(mapa)

    for _, teren in tereni.iterrows():
        centar = teren.geometry.representative_point()
        folium.Marker(
            location=[centar.y, centar.x],
            icon=DivIcon(
                icon_size=(105, 22),
                icon_anchor=(52, 11),
                html=(
                    '<div style="background:#ffffffcc;border:1px solid #333;'
                    'padding:2px;text-align:center;font-size:11px;font-weight:bold;">'
                    f"{int(teren['osm_id'])}</div>"
                ),
            ),
        ).add_to(mapa)


def napravi_mapu(
    naziv_sloja: str | None = None,
    prikazi_terene: bool = False,
) -> folium.Map:
    """Napravi zajednicku mapu za pregled ili crtanje izabranog sloja."""

    min_x, min_y, max_x, max_y = OKVIR_KAMPUSA
    mapa = folium.Map(
        location=[(min_y + max_y) / 2, (min_x + max_x) / 2],
        zoom_start=16,
        tiles=None,
        control_scale=True,
    )
    _dodaj_raster(mapa, preuzmi_raster_kampusa())

    zone = gpd.read_file(PUTANJA_ZONA)
    folium.GeoJson(
        zone,
        name="Zone kampusa",
        style_function=lambda _: {
            "color": "#00b7ff",
            "weight": 3,
            "fillColor": "#00b7ff",
            "fillOpacity": 0.05,
        },
        tooltip=folium.GeoJsonTooltip(fields=["naziv"], aliases=["Zona"]),
    ).add_to(mapa)
    dodaj_sacuvane_slojeve(mapa)

    if prikazi_terene:
        dodaj_geofabrik_terene(mapa)

    if naziv_sloja is not None:
        geometrija = SLOJEVI_ZA_CRTANJE[naziv_sloja]["geometrija"]
        Draw(
            export=False,
            draw_options={
                "polyline": False,
                "rectangle": False,
                "circle": False,
                "marker": geometrija == "Point",
                "circlemarker": False,
                "polygon": (
                    {"allowIntersection": False, "showArea": True}
                    if geometrija == "Polygon"
                    else False
                ),
            },
            edit_options={"edit": True, "remove": True},
        ).add_to(mapa)

    folium.LayerControl(collapsed=False).add_to(mapa)
    mapa.fit_bounds([[min_y, min_x], [max_y, max_x]])
    return mapa


def formatiraj_red(naziv_sloja: str, objekat_id: int, red: pd.Series) -> str:
    """Vrati citljiv opis SQL reda u padajucoj listi."""

    if naziv_sloja == "Parkiralista":
        return f"{red['naziv']} — {red['zona']} — {red['tip']}"
    if naziv_sloja == "Zelene povrsine":
        return f"zelena_povrsina_{objekat_id} — {red['zona']} — {red['tip']}"
    return f"{red['naziv']} — {red['zona']} — {red['stanje']}"


st.title("GisCampus prostorni slojevi")
prikaz = st.segmented_control(
    "Prikaz",
    ["Pregled", *SLOJEVI_ZA_CRTANJE, "Tereni"],
    default="Infrastrukturni objekti",
    key="prikaz_sloja",
)

if prikaz == "Pregled":
    st.write("Ukljuci ili iskljuci sacuvane slojeve pomocu kontrole na mapi.")
    st_folium(
        napravi_mapu(),
        width=None,
        height=720,
        key="pregled_slojeva",
        returned_objects=[],
    )
elif prikaz == "Tereni":
    st.write(
        "OSM ID je ispisan preko svakog poligona. Prelaskom misa vidi se i "
        "povrsina terena."
    )
    tereni = ucitaj_geofabrik_terene().sort_values("osm_id")
    st_folium(
        napravi_mapu(prikazi_terene=True),
        width=None,
        height=720,
        key="provera_geofabrik_terena",
        returned_objects=[],
    )
    st.dataframe(
        tereni[["osm_id", "povrsina_m2"]].reset_index(drop=True),
        hide_index=True,
    )
else:
    konfiguracija = SLOJEVI_ZA_CRTANJE[prikaz]
    redovi = ucitaj_redove_iz_baze(prikaz)
    id_kolona = konfiguracija["id_kolona"]
    redovi_po_id = redovi.set_index(id_kolona)
    izabrani_id = st.selectbox(
        "Objekat koji crtas",
        options=redovi[id_kolona].tolist(),
        format_func=lambda identifikator: formatiraj_red(
            prikaz,
            identifikator,
            redovi_po_id.loc[identifikator],
        ),
        key=f"izabrani_objekat_{prikaz}",
    )
    izabrani_red = redovi_po_id.loc[izabrani_id]
    sacuvani = ucitaj_sacuvani_sloj(prikaz)

    rezultat = st_folium(
        napravi_mapu(prikaz),
        width=None,
        height=720,
        key=f"crtanje_{prikaz}_{izabrani_id}",
        returned_objects=["all_drawings"],
    )
    crtezi = rezultat.get("all_drawings") or []
    kljuc_crteza = f"crtez_{prikaz}_{izabrani_id}"
    if crtezi:
        st.session_state[kljuc_crteza] = crtezi[-1]["geometry"]

    if st.button("Sacuvaj izabrani objekat", type="primary"):
        geometrija = st.session_state.get(kljuc_crteza)
        if geometrija is None:
            st.error("Prvo nacrtaj geometriju na mapi.")
        else:
            try:
                sacuvaj_geometriju(
                    prikaz,
                    izabrani_id,
                    izabrani_red,
                    geometrija,
                )
                st.session_state.pop(kljuc_crteza, None)
                st.success("Objekat je sacuvan.")
                st.rerun()
            except ValueError as greska:
                st.error(str(greska))

    sacuvani_id = (
        set(sacuvani[id_kolona].astype(int)) if not sacuvani.empty else set()
    )
    st.write(f"Sacuvano: {len(sacuvani_id)} od {len(redovi)} objekata")
