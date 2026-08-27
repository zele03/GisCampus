"""Interaktivna aplikacija GisCampus."""

import folium
import geopandas as gpd
import pandas as pd
import streamlit as st
from folium.plugins import Draw
from shapely.geometry import shape
from streamlit_folium import st_folium

from src.giscampus.geo.data import (
    KOREN_PROJEKTA,
    OKVIR_KAMPUSA,
    preuzmi_raster_kampusa,
)
from src.giscampus.geo.analysis import PUTANJA_ZONA
from src.giscampus.geo.map import _dodaj_raster

PUTANJA_NACRTANIH_ZONA = (
    KOREN_PROJEKTA / "data" / "processed" / "campus" / "zone_nacrtane.geojson"
)

OBJEKTI_ZA_CRTANJE = {
    "Okvir celog kampusa": "okvir_kampusa",
    "Severna zona": "Severna",
    "Juzna zona": "Juzna",
    "Istocna zona": "Istocna",
    "Zapadna zona": "Zapadna",
    "Centralna zona": "Centralna",
}


def ucitaj_sacuvane_zone() -> gpd.GeoDataFrame:
    """Ucitaj ranije sacuvane crteze ili vrati prazan GeoDataFrame."""

    if PUTANJA_NACRTANIH_ZONA.exists():
        return gpd.read_file(PUTANJA_NACRTANIH_ZONA)

    return gpd.GeoDataFrame(
        {"naziv": []},
        geometry=gpd.GeoSeries([], crs="EPSG:4326"),
    )


def sacuvaj_poligon(naziv: str, geojson_geometrija: dict) -> None:
    """Sacuvaj novi poligon ili zameni raniji poligon istog naziva."""

    geometrija = shape(geojson_geometrija)
    if geometrija.geom_type != "Polygon":
        raise ValueError("Potrebno je nacrtati poligon.")
    if not geometrija.is_valid:
        raise ValueError("Nacrtani poligon nije geometrijski ispravan.")

    zone = ucitaj_sacuvane_zone()
    zone = zone[zone["naziv"] != naziv]
    novi_red = gpd.GeoDataFrame(
        [{"naziv": naziv, "geometry": geometrija}],
        geometry="geometry",
        crs="EPSG:4326",
    )
    zone = gpd.GeoDataFrame(
        pd.concat([zone, novi_red], ignore_index=True),
        geometry="geometry",
        crs="EPSG:4326",
    )

    PUTANJA_NACRTANIH_ZONA.parent.mkdir(parents=True, exist_ok=True)
    zone.to_file(PUTANJA_NACRTANIH_ZONA, driver="GeoJSON")


def napravi_mapu_za_crtanje(zone: gpd.GeoDataFrame) -> folium.Map:
    """Napravi mapu sa rasterom, sacuvanim zonama i alatom za crtanje."""

    min_x, min_y, max_x, max_y = OKVIR_KAMPUSA
    mapa = folium.Map(
        location=[(min_y + max_y) / 2, (min_x + max_x) / 2],
        zoom_start=16,
        tiles=None,
        control_scale=True,
    )
    _dodaj_raster(mapa, preuzmi_raster_kampusa())

    if not zone.empty:
        folium.GeoJson(
            zone,
            name="Sacuvani crtezi",
            style_function=lambda _: {
                "color": "#00b7ff",
                "weight": 3,
                "fillColor": "#00b7ff",
                "fillOpacity": 0.12,
            },
            tooltip=folium.GeoJsonTooltip(fields=["naziv"], aliases=["Naziv"]),
            show=False,
        ).add_to(mapa)

    if PUTANJA_ZONA.exists():
        ociscene_zone = gpd.read_file(PUTANJA_ZONA)
        folium.GeoJson(
            ociscene_zone,
            name="Ociscene zone",
            style_function=lambda _: {
                "color": "#00d084",
                "weight": 3,
                "fillColor": "#00d084",
                "fillOpacity": 0.16,
            },
            tooltip=folium.GeoJsonTooltip(
                fields=["naziv", "povrsina_m2"],
                aliases=["Zona", "Povrsina m2"],
            ),
        ).add_to(mapa)

    Draw(
        export=False,
        draw_options={
            "polyline": False,
            "rectangle": False,
            "circle": False,
            "marker": False,
            "circlemarker": False,
            "polygon": {
                "allowIntersection": False,
                "showArea": True,
            },
        },
        edit_options={"edit": True, "remove": True},
    ).add_to(mapa)
    folium.LayerControl(collapsed=False).add_to(mapa)
    mapa.fit_bounds([[min_y, min_x], [max_y, max_x]])
    return mapa


def main() -> None:
    """Prikazi ekran za rucno crtanje okvira kampusa i zona."""

    st.set_page_config(page_title="GisCampus", layout="wide")
    st.title("Crtanje kampusa i zona")
    st.write(
        "Izaberi objekat, nacrtaj jedan poligon pomocu alata sa leve strane "
        "mape i zatim ga sacuvaj."
    )

    izbor = st.selectbox("Objekat koji crtas", list(OBJEKTI_ZA_CRTANJE))
    naziv = OBJEKTI_ZA_CRTANJE[izbor]
    zone = ucitaj_sacuvane_zone()
    rezultat = st_folium(
        napravi_mapu_za_crtanje(zone),
        width=None,
        height=720,
        key=f"crtanje_{naziv}",
        returned_objects=["all_drawings"],
    )

    crtezi = rezultat.get("all_drawings") or []
    if crtezi:
        st.session_state[f"crtez_{naziv}"] = crtezi[-1]["geometry"]

    if st.button("Sacuvaj izabrani poligon", type="primary"):
        geometrija = st.session_state.get(f"crtez_{naziv}")
        if geometrija is None:
            st.error("Prvo nacrtaj poligon na mapi.")
        else:
            try:
                sacuvaj_poligon(naziv, geometrija)
                st.success(f"Sacuvan je poligon: {izbor}.")
                st.rerun()
            except ValueError as greska:
                st.error(str(greska))

    sacuvani_nazivi = set(zone["naziv"]) if not zone.empty else set()
    st.write(f"Sacuvano: {len(sacuvani_nazivi)} od {len(OBJEKTI_ZA_CRTANJE)} objekata")


if __name__ == "__main__":
    main()
