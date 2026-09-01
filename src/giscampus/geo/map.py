"""Interaktivni prikaz rastera i predlozenih geometrija zgrada."""

from pathlib import Path

import folium
import geopandas as gpd
import numpy as np
import rasterio
from folium.raster_layers import ImageOverlay
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

from .data import (
    KOREN_PROJEKTA,
    OKVIR_KAMPUSA,
    preuzmi_raster_kampusa,
    ucitaj_shp_sloj,
)

PUTANJA_INTERAKTIVNE_MAPE = (
    KOREN_PROJEKTA / "data" / "outputs" / "provera_zgrada.html"
)

# OSM ID vrednosti povezuju red iz SQL tabele sa jednim ili vise SHP poligona.
# Spisak je predlog koji je prvo proveraen na mapi, pa se tek zatim upisan u bazu.
OSM_POLIGONI_ZGRADA = {
    "Tehnoloski fakultet": [222832767],
    "Poljoprivredni fakultet": [2956836],
    "Pravni fakultet": [222832764],
    "Filozofski fakultet": [222832769],
    "Fakultet tehnickih nauka": [
        250277314,
        250277315,
        250277316,
        250277317,
        222832768,
        148672026,
    ],
    "Prirodno-matematicki fakultet": [
        222832759,
        222832773,
        250277341,
        250277345,
        250277348,
        250277356,
        250277360,
    ],
    "Ekonomski fakultet": [222832762],
    "Visoka poslovna skola": [776263168],
    "Naucno-tehnoloski park": [17305144],
    "Studentski dom Slobodan Bajic": [2955597],
    "Studentski dom Veljko Vlahovic": [2955596],
    "Veseli vrtic": [20191834],
    "Rektorat": [19969758],
    "Institut BioSens": [1098557258],
}

# Veza izmedju naziva terena u SQL tabeli i poligona iz OSM SHP sloja.
# ID vrednosti su rucno proverene na interaktivnoj mapi.
OSM_POLIGONI_TERENA = {
    "Teren za fudbal": 222834316,
    "Teren za mali fudbal 1": 222834322,
    "Teren za kosarku 1": 222834323,
    "Teren za mali fudbal 2": 222834324,
    "Teren za kosarku 2": 222834325,
    "Teren za odbojku": 222834326,
    "Teren za tenis": 222834327,
    "Teren za mali fudbal 3": 222834329,
}

BOJE_ZGRADA = [
    "#e41a1c",
    "#377eb8",
    "#4daf4a",
    "#984ea3",
    "#ff7f00",
    "#a65628",
    "#f781bf",
    "#1b9e77",
]

def _ka_multipoligonu(geometrije: gpd.GeoSeries) -> MultiPolygon:
    """Spoji izabrane delove i rezultat uvek vrati kao MultiPolygon."""

    spojena = unary_union(geometrije.to_list())
    if isinstance(spojena, Polygon):
        return MultiPolygon([spojena])
    if isinstance(spojena, MultiPolygon):
        return spojena

    poligoni = [deo for deo in spojena.geoms if isinstance(deo, Polygon)]
    return MultiPolygon(poligoni)


def pripremi_predloge_zgrada() -> gpd.GeoDataFrame:
    """Izdvoji SHP poligone predlozene za redove iz SQL tabele zgrade."""

    osm_zgrade = ucitaj_shp_sloj("zgrade")
    redovi = []

    for naziv, osm_id_vrednosti in OSM_POLIGONI_ZGRADA.items():
        delovi = osm_zgrade[osm_zgrade["osm_id"].astype(int).isin(osm_id_vrednosti)]
        if len(delovi) != len(osm_id_vrednosti):
            pronadjeni = set(delovi["osm_id"].astype(int))
            nedostaju = sorted(set(osm_id_vrednosti) - pronadjeni)
            raise RuntimeError(f"Za zgradu '{naziv}' nedostaju OSM poligoni: {nedostaju}")

        redovi.append(
            {
                "naziv": naziv,
                "osm_id": ", ".join(map(str, osm_id_vrednosti)),
                "broj_delova": len(osm_id_vrednosti),
                "geometrija": _ka_multipoligonu(delovi.geometry),
            }
        )

    return gpd.GeoDataFrame(redovi, geometry="geometrija", crs=osm_zgrade.crs)


def pripremi_predloge_terena() -> gpd.GeoDataFrame:
    """Povezi nazive terena iz SQL tabele sa rucno proverenim OSM poligonima."""

    osm_poligoni = ucitaj_shp_sloj("poligonski_objekti")
    osm_id_brojevi = osm_poligoni["osm_id"].astype(int)
    redovi = []

    for naziv, osm_id in OSM_POLIGONI_TERENA.items():
        pronadjeni = osm_poligoni[osm_id_brojevi == osm_id]
        if len(pronadjeni) != 1:
            raise RuntimeError(
                f"Za teren '{naziv}' ocekuje se jedan OSM poligon sa ID {osm_id}, "
                f"a pronadjeno je: {len(pronadjeni)}."
            )

        redovi.append(
            {
                "naziv": naziv,
                "osm_id": osm_id,
                "geometrija": pronadjeni.geometry.iloc[0],
            }
        )

    return gpd.GeoDataFrame(redovi, geometry="geometrija", crs=osm_poligoni.crs)


def _dodaj_raster(mapa: folium.Map, putanja_rastera: Path) -> None:
    """Dodaj lokalni raster kao podlogu interaktivne mape."""

    with rasterio.open(putanja_rastera) as raster:
        slika = np.moveaxis(raster.read([1, 2, 3]), 0, 2)
        granice = [[raster.bounds.bottom, raster.bounds.left], [raster.bounds.top, raster.bounds.right]]

    ImageOverlay(
        image=slika,
        bounds=granice,
        name="Esri World Imagery raster",
        opacity=1,
        interactive=True,
        cross_origin=False,
        zindex=1,
    ).add_to(mapa)


def napravi_interaktivnu_mapu(
    putanja_izlaza: Path = PUTANJA_INTERAKTIVNE_MAPE,
) -> Path:
    """Napravi HTML mapu za rucnu proveru predlozenih poligona zgrada."""

    raster = preuzmi_raster_kampusa()
    sve_zgrade = ucitaj_shp_sloj("zgrade")
    predlozi = pripremi_predloge_zgrada()
    min_x, min_y, max_x, max_y = OKVIR_KAMPUSA

    mapa = folium.Map(
        location=[(min_y + max_y) / 2, (min_x + max_x) / 2],
        zoom_start=16,
        tiles=None,
        control_scale=True,
    )
    _dodaj_raster(mapa, raster)
    mapa.get_root().html.add_child(
        folium.Element(
            '<div style="position:fixed;bottom:2px;right:4px;z-index:9999;'
            'background:white;padding:2px 5px;font-size:10px;">'
            'Raster: Esri World Imagery i dobavljaci snimaka</div>'
        )
    )

    folium.GeoJson(
        sve_zgrade,
        name="Sve OSM zgrade",
        style_function=lambda _: {
            "color": "#666666",
            "weight": 1,
            "fillColor": "#ffffff",
            "fillOpacity": 0.05,
        },
        tooltip=folium.GeoJsonTooltip(fields=["osm_id", "name"], aliases=["OSM ID", "OSM naziv"]),
        show=False,
    ).add_to(mapa)

    for indeks, red in predlozi.iterrows():
        sloj = gpd.GeoDataFrame([red], geometry="geometrija", crs=predlozi.crs)
        boja = BOJE_ZGRADA[indeks % len(BOJE_ZGRADA)]
        folium.GeoJson(
            sloj,
            name=red["naziv"],
            style_function=lambda _, boja=boja: {
                "color": boja,
                "weight": 3,
                "fillColor": boja,
                "fillOpacity": 0.28,
            },
            tooltip=folium.GeoJsonTooltip(
                fields=["naziv", "osm_id", "broj_delova"],
                aliases=["SQL zgrada", "OSM ID", "Broj poligona"],
            ),
        ).add_to(mapa)

    folium.LayerControl(collapsed=False).add_to(mapa)
    mapa.fit_bounds([[min_y, min_x], [max_y, max_x]])
    putanja_izlaza.parent.mkdir(parents=True, exist_ok=True)
    mapa.save(putanja_izlaza)
    return putanja_izlaza


if __name__ == "__main__":
    napravi_interaktivnu_mapu()
