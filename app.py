"""GisCampus aplikacija za pregled slojeva i CRUD rad sa podacima."""

import re
from warnings import catch_warnings, simplefilter

import folium
import geopandas as gpd
import streamlit as st
from branca.element import Element, MacroElement, Template
from folium.plugins import Draw
from psycopg2 import Error as PostgreSQLError
from shapely.geometry import shape
from streamlit_folium import st_folium

from src.giscampus.geo.analysis import (
    analiza_buffera_infrastrukture,
    analiza_clip_zgrada,
    analiza_infrastrukture_u_centralnoj_zoni,
    analiza_preklapanja_parkinga_i_zgrada,
    analiza_preseka_parkinga_i_zelenila,
    analiza_slobodne_povrsine_kampusa,
    analiza_unije_parkinga_i_zelenila,
)
from src.giscampus.geo.data import OKVIR_KAMPUSA, preuzmi_raster_kampusa
from src.giscampus.geo.map import _dodaj_raster
from src.giscampus.sql.crud import (
    azuriraj_red,
    dodaj_prostorni_red,
    obrisi_red,
    prikazi_sve,
    pronadji_zonu_za_geometriju,
)
from src.giscampus.sql.database import povezi_se

st.set_page_config(page_title="GisCampus", page_icon=":material/map:", layout="wide")

SLOJEVI = {
    "Zone kampusa": {
        "tabela": "zone_kampusa",
        "id": "zona_id",
        "upit": """
            SELECT zona_id, naziv, oznaka, povrsina_m2,
                   ST_Transform(geometrija, 4326) AS geometrija
            FROM zone_kampusa WHERE geometrija IS NOT NULL ORDER BY zona_id;
        """,
        "polja": ["naziv", "oznaka", "povrsina_m2"],
        "nazivi_polja": ["Zona", "Oznaka", "Povrsina m2"],
        "geometrija": "Polygon",
        "boja": "#00b7ff",
    },
    "Zgrade": {
        "tabela": "zgrade",
        "id": "zgrada_id",
        "upit": """
            SELECT zgrada_id, naziv, tip, povrsina_m2,
                   ST_Transform(geometrija, 4326) AS geometrija
            FROM zgrade WHERE geometrija IS NOT NULL ORDER BY zgrada_id;
        """,
        "polja": ["naziv", "tip", "povrsina_m2"],
        "nazivi_polja": ["Naziv", "Tip", "Povrsina m2"],
        "geometrija": "Polygon",
        "boja": "#8e44ad",
    },
    "Parkiralista": {
        "tabela": "parkiralista",
        "id": "parkiraliste_id",
        "upit": """
            SELECT parkiraliste_id, naziv, tip, povrsina_m2,
                   ST_Transform(geometrija, 4326) AS geometrija
            FROM parkiralista WHERE geometrija IS NOT NULL
            ORDER BY parkiraliste_id;
        """,
        "polja": ["naziv", "tip", "povrsina_m2"],
        "nazivi_polja": ["Naziv", "Tip", "Povrsina m2"],
        "geometrija": "Polygon",
        "boja": "#ff3b30",
    },
    "Zelene povrsine": {
        "tabela": "zelene_povrsine",
        "id": "zelena_povrsina_id",
        "upit": """
            SELECT zelena_povrsina_id, tip, povrsina_m2,
                   ST_Transform(geometrija, 4326) AS geometrija
            FROM zelene_povrsine WHERE geometrija IS NOT NULL
            ORDER BY zelena_povrsina_id;
        """,
        "polja": ["tip", "povrsina_m2"],
        "nazivi_polja": ["Tip", "Povrsina m2"],
        "geometrija": "Polygon",
        "boja": "#00a651",
    },
    "Infrastrukturni objekti": {
        "tabela": "infrastrukturni_objekti",
        "id": "infrastrukturni_objekat_id",
        "upit": """
            SELECT infrastrukturni_objekat_id, naziv, stanje,
                   ST_Transform(geometrija, 4326) AS geometrija
            FROM infrastrukturni_objekti WHERE geometrija IS NOT NULL
            ORDER BY infrastrukturni_objekat_id;
        """,
        "polja": ["naziv", "stanje"],
        "nazivi_polja": ["Naziv", "Stanje"],
        "geometrija": "Point",
        "boja": "#ff9500",
    },
    "Tereni": {
        "tabela": "tereni",
        "id": "teren_id",
        "upit": """
            SELECT teren_id, naziv, povrsina_m2,
                   ST_Transform(geometrija, 4326) AS geometrija
            FROM tereni WHERE geometrija IS NOT NULL ORDER BY teren_id;
        """,
        "polja": ["naziv", "povrsina_m2"],
        "nazivi_polja": ["Naziv", "Povrsina m2"],
        "geometrija": "Polygon",
        "boja": "#ffd60a",
    },
}

CRUD_TABELE = {
    "Zone kampusa": {
        "tabela": "zone_kampusa",
        "id": "zona_id",
        "kolone": ["naziv", "oznaka"],
        "geometrija": "Polygon",
        "ima_povrsinu": True,
    },
    "Zgrade": {
        "tabela": "zgrade",
        "id": "zgrada_id",
        "kolone": ["naziv", "tip"],
        "geometrija": "Polygon",
        "ima_povrsinu": True,
    },
    "Parkiralista": {
        "tabela": "parkiralista",
        "id": "parkiraliste_id",
        "kolone": ["naziv", "tip"],
        "geometrija": "Polygon",
        "ima_povrsinu": True,
    },
    "Zelene povrsine": {
        "tabela": "zelene_povrsine",
        "id": "zelena_povrsina_id",
        "kolone": ["tip"],
        "geometrija": "Polygon",
        "ima_povrsinu": True,
    },
    "Infrastrukturni objekti": {
        "tabela": "infrastrukturni_objekti",
        "id": "infrastrukturni_objekat_id",
        "kolone": ["naziv", "stanje"],
        "geometrija": "Point",
        "ima_povrsinu": False,
    },
    "Tereni": {
        "tabela": "tereni",
        "id": "teren_id",
        "kolone": ["naziv"],
        "geometrija": "Polygon",
        "ima_povrsinu": True,
    },
}

ANALIZE = {
    "Bez analize": None,
    "Clip - zgrade u Severnoj zoni": analiza_clip_zgrada,
    "Intersection - parking i zelenilo": analiza_preseka_parkinga_i_zelenila,
    "Union - zelene povrsine i parkinzi": analiza_unije_parkinga_i_zelenila,
    "Difference - kampus bez zgrada": analiza_slobodne_povrsine_kampusa,
    "Buffer - 30 m oko infrastrukture": analiza_buffera_infrastrukture,
    "Within - infrastruktura u Centralnoj zoni": (
        analiza_infrastrukture_u_centralnoj_zoni
    ),
    "Overlaps - parkinzi i zgrade": analiza_preklapanja_parkinga_i_zgrada,
}


@st.cache_data(ttl="5m", max_entries=10)
def ucitaj_postgis_sloj(naziv_sloja: str) -> gpd.GeoDataFrame:
    """Ucitaj geometrije jednog sloja direktno iz PostGIS baze."""

    with povezi_se() as konekcija, catch_warnings():
        simplefilter("ignore", UserWarning)
        return gpd.read_postgis(
            SLOJEVI[naziv_sloja]["upit"],
            konekcija,
            geom_col="geometrija",
            crs="EPSG:4326",
        )


def dodaj_postgis_slojeve(
    mapa: folium.Map,
    prikazi_slojeve: bool = True,
    izabrani_objekat: dict | None = None,
) -> dict[str, folium.GeoJson]:
    """Dodaj PostGIS slojeve i odredi njihovu pocetnu vidljivost."""

    folium_slojevi = {}
    for naziv, konfiguracija in SLOJEVI.items():
        podaci = ucitaj_postgis_sloj(naziv)
        boja = konfiguracija["boja"]
        tabela = konfiguracija["tabela"]
        id_kolona = konfiguracija["id"]
        podaci = podaci.copy()
        podaci["_gis_izbor"] = podaci[id_kolona].map(
            lambda red_id, tabela=tabela: f"GIS_IZBOR:{tabela}:{int(red_id)}"
        )

        if konfiguracija["geometrija"] == "Point":
            grupa = folium.FeatureGroup(
                name=naziv,
                show=prikazi_slojeve,
            ).add_to(mapa)
            for _, red in podaci.iterrows():
                red_id = int(red[id_kolona])
                izabran = (
                    izabrani_objekat is not None
                    and izabrani_objekat["tabela"] == tabela
                    and izabrani_objekat["id"] == red_id
                )
                klasa_pina = "gis-pin gis-pin--izabran" if izabran else "gis-pin"
                sadrzaj_opisa = "<br>".join(
                    f"<b>{oznaka}:</b> {red[polje]}"
                    for polje, oznaka in zip(
                        konfiguracija["polja"],
                        konfiguracija["nazivi_polja"],
                        strict=True,
                    )
                )
                folium.Marker(
                    location=[red.geometrija.y, red.geometrija.x],
                    icon=folium.DivIcon(
                        html=(
                            f'<div class="{klasa_pina}" '
                            f'style="--pin-color:{boja}"></div>'
                        ),
                        icon_size=(28, 34),
                        icon_anchor=(14, 32),
                        class_name="gis-pin-okvir",
                    ),
                    tooltip=folium.Tooltip(sadrzaj_opisa),
                    popup=folium.Popup(f"GIS_IZBOR:{tabela}:{red_id}"),
                ).add_to(grupa)
            folium_slojevi[naziv] = grupa
            continue

        def stil_objekta(
            objekat,
            boja=boja,
            tabela=tabela,
            id_kolona=id_kolona,
        ):
            """Vrati osnovni ili naglaseni stil jednog objekta."""

            izabran = (
                izabrani_objekat is not None
                and izabrani_objekat["tabela"] == tabela
                and int(objekat["properties"][id_kolona])
                == izabrani_objekat["id"]
            )
            if izabran:
                return {
                    "color": "#ffff00",
                    "weight": 7,
                    "fillColor": "#ffff00",
                    "fillOpacity": 0.55,
                }
            return {
                "color": boja,
                "weight": 3,
                "fillColor": boja,
                "fillOpacity": 0.25,
            }

        opcije = {
            "name": naziv,
            "show": prikazi_slojeve,
            "style_function": stil_objekta,
            "tooltip": folium.GeoJsonTooltip(
                fields=konfiguracija["polja"],
                aliases=konfiguracija["nazivi_polja"],
            ),
            "popup": folium.GeoJsonPopup(
                fields=["_gis_izbor"],
                aliases=["Izabrani objekat"],
            ),
        }
        folium_slojevi[naziv] = folium.GeoJson(podaci, **opcije).add_to(mapa)

    return folium_slojevi


class KontrolaSimbologije(MacroElement):
    """Leaflet kontrola za promenu stila direktno na mapi."""

    _template = Template(
        """
        {% macro script(this, kwargs) %}
        const gisSlojevi = {
            {% for naziv, sloj in this.slojevi.items() %}
            {{ naziv|tojson }}: {{ sloj.get_name() }},
            {% endfor %}
        };
        const gisStilovi = {
            {% for naziv, stil in this.stilovi.items() %}
            {{ naziv|tojson }}: {
                boja: {{ stil.boja|tojson }},
                providnost: {{ stil.providnost }},
                debljina: {{ stil.debljina }}
            },
            {% endfor %}
        };

        const kontrolaStila = L.control({position: "topleft"});
        kontrolaStila.onAdd = function() {
            const okvir = L.DomUtil.create("div", "leaflet-bar");
            okvir.style.background = "white";
            okvir.style.color = "#202124";
            okvir.style.padding = "0";

            const dugme = L.DomUtil.create("button", "", okvir);
            dugme.type = "button";
            dugme.title = "Promeni simbologiju";
            dugme.textContent = "Stil";
            dugme.style.width = "44px";
            dugme.style.height = "30px";
            dugme.style.border = "0";
            dugme.style.background = "white";
            dugme.style.color = "#202124";
            dugme.style.cursor = "pointer";
            dugme.style.fontWeight = "600";

            const panel = L.DomUtil.create("div", "", okvir);
            panel.style.display = "none";
            panel.style.width = "210px";
            panel.style.padding = "9px";
            panel.style.font = "12px sans-serif";
            panel.style.color = "#202124";
            panel.innerHTML = `
                <div style="font-weight:600;margin-bottom:3px">Sloj</div>
                <select data-polje="sloj" style="width:100%;margin-bottom:9px"></select>
                <div style="font-weight:600;margin-bottom:3px">Boja</div>
                <input data-polje="boja" type="color"
                       style="width:100%;height:28px;margin-bottom:9px">
                <div style="font-weight:600">Providnost</div>
                <input data-polje="providnost" type="range" min="0" max="1"
                       step="0.05" style="width:100%;margin-bottom:7px">
                <div style="font-weight:600">Debljina ivice</div>
                <input data-polje="debljina" type="range" min="1" max="6"
                       step="1" style="width:100%">
            `;

            const izbor = panel.querySelector('[data-polje="sloj"]');
            const boja = panel.querySelector('[data-polje="boja"]');
            const providnost = panel.querySelector('[data-polje="providnost"]');
            const debljina = panel.querySelector('[data-polje="debljina"]');

            Object.keys(gisSlojevi).forEach(function(naziv) {
                const opcija = document.createElement("option");
                opcija.value = naziv;
                opcija.textContent = naziv;
                izbor.appendChild(opcija);
            });

            function ucitajStil() {
                const stil = gisStilovi[izbor.value];
                boja.value = stil.boja;
                providnost.value = stil.providnost;
                debljina.value = stil.debljina;
            }

            function promeniStil() {
                const stil = gisStilovi[izbor.value];
                stil.boja = boja.value;
                stil.providnost = Number(providnost.value);
                stil.debljina = Number(debljina.value);
                gisSlojevi[izbor.value].setStyle({
                    color: stil.boja,
                    fillColor: stil.boja,
                    fillOpacity: stil.providnost,
                    weight: stil.debljina
                });
                gisSlojevi[izbor.value].eachLayer(function(objekat) {
                    const element = objekat.getElement ? objekat.getElement() : null;
                    const pin = element ? element.querySelector(".gis-pin") : null;
                    if (pin) {
                        pin.style.setProperty("--pin-color", stil.boja);
                        pin.style.opacity = stil.providnost;
                        pin.style.borderWidth = stil.debljina + "px";
                    }
                });
            }

            dugme.addEventListener("click", function() {
                panel.style.display = panel.style.display === "none" ? "block" : "none";
            });
            izbor.addEventListener("change", ucitajStil);
            boja.addEventListener("input", promeniStil);
            providnost.addEventListener("input", promeniStil);
            debljina.addEventListener("input", promeniStil);
            L.DomEvent.disableClickPropagation(okvir);
            L.DomEvent.disableScrollPropagation(okvir);
            ucitajStil();
            return okvir;
        };
        kontrolaStila.addTo({{ this._parent.get_name() }});
        {% endmacro %}
        """
    )

    def __init__(self, slojevi: dict[str, folium.GeoJson]) -> None:
        super().__init__()
        self._name = "KontrolaSimbologije"
        self.slojevi = slojevi
        self.stilovi = {
            naziv: {
                "boja": SLOJEVI[naziv]["boja"],
                "providnost": (
                    1.0 if SLOJEVI[naziv]["geometrija"] == "Point" else 0.25
                ),
                "debljina": 3,
            }
            for naziv in slojevi
        }


class IskljuciProzoreObjekata(MacroElement):
    """Zadrzi podatak o kliku, ali ne otvaraj Leaflet popup."""

    _template = Template(
        """
        {% macro script(this, kwargs) %}
        {% for sloj in this.slojevi.values() %}
        {{ sloj.get_name() }}.eachLayer(function(objekat) {
            if (objekat.getPopup && objekat.getPopup()) {
                objekat.off("click", objekat._openPopup, objekat);
            }
        });
        {% endfor %}
        {% endmacro %}
        """
    )

    def __init__(self, slojevi: dict[str, folium.GeoJson]) -> None:
        super().__init__()
        self._name = "IskljuciProzoreObjekata"
        self.slojevi = slojevi


@st.cache_data(ttl="5m", max_entries=10)
def pokreni_analizu(naziv_analize: str) -> gpd.GeoDataFrame:
    """Pokreni izabranu prostornu analizu i kesiraj njen rezultat."""

    funkcija = ANALIZE[naziv_analize]
    if funkcija is None:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:32634")
    return funkcija()


def dodaj_rezultat_analize(
    mapa: folium.Map,
    naziv_analize: str,
    rezultat: gpd.GeoDataFrame,
) -> None:
    """Dodaj rezultat izabrane analize kao poseban sloj na mapi."""

    if rezultat.empty:
        return

    sloj = rezultat.to_crs(4326).copy()
    opcije = {
        "name": f"Analiza: {naziv_analize}",
        "style_function": lambda _: {
            "color": "#ff00c8",
            "weight": 4,
            "fillColor": "#ff00c8",
            "fillOpacity": 0.35,
        },
        "tooltip": folium.GeoJsonTooltip(
            fields=["analiza"],
            aliases=["Rezultat"],
        ),
    }
    if (sloj.geometry.geom_type == "Point").all():
        opcije["marker"] = folium.CircleMarker(radius=8)

    folium.GeoJson(sloj, **opcije).add_to(mapa)


def napravi_mapu(
    naziv_analize: str = "Bez analize",
    rezultat_analize: gpd.GeoDataFrame | None = None,
    geometrija_za_crtanje: str | None = None,
    sacuvana_geometrija=None,
    izabrani_objekat: dict | None = None,
) -> folium.Map:
    """Napravi zavrsnu mapu sa rasterom i svim PostGIS slojevima."""

    min_x, min_y, max_x, max_y = OKVIR_KAMPUSA
    mapa = folium.Map(
        location=[(min_y + max_y) / 2, (min_x + max_x) / 2],
        zoom_start=16,
        tiles=None,
        control_scale=False,
    )
    mapa.get_root().header.add_child(
        Element(
            """
            <style>
            .leaflet-interactive:focus { outline: none !important; }
            .gis-pin-okvir {
                background: transparent !important;
                border: 0 !important;
            }
            .gis-pin {
                width: 24px;
                height: 24px;
                background: var(--pin-color);
                border: 3px solid white;
                border-radius: 50% 50% 50% 0;
                box-shadow: 0 2px 5px rgba(0, 0, 0, 0.55);
                transform: rotate(-45deg);
            }
            .gis-pin::after {
                content: "";
                position: absolute;
                width: 7px;
                height: 7px;
                top: 6px;
                left: 6px;
                background: white;
                border-radius: 50%;
            }
            .gis-pin--izabran {
                background: #ffff00 !important;
                border-color: #111111 !important;
                transform: rotate(-45deg) scale(1.25);
            }
            </style>
            """
        )
    )
    _dodaj_raster(mapa, preuzmi_raster_kampusa())
    prikazi_osnovne_slojeve = naziv_analize == "Bez analize"
    slojevi = dodaj_postgis_slojeve(
        mapa,
        prikazi_osnovne_slojeve,
        izabrani_objekat,
    )
    IskljuciProzoreObjekata(slojevi).add_to(mapa)
    KontrolaSimbologije(slojevi).add_to(mapa)
    if rezultat_analize is not None:
        dodaj_rezultat_analize(mapa, naziv_analize, rezultat_analize)
    if sacuvana_geometrija is not None:
        nacrtani_sloj = gpd.GeoDataFrame(
            [{"naziv": "Nova geometrija", "geometry": sacuvana_geometrija}],
            geometry="geometry",
            crs="EPSG:32634",
        ).to_crs(4326)
        folium.GeoJson(
            nacrtani_sloj,
            name="Nova geometrija",
            style_function=lambda _: {
                "color": "#ff00c8",
                "weight": 4,
                "fillColor": "#ff00c8",
                "fillOpacity": 0.3,
            },
            marker=folium.CircleMarker(radius=8),
        ).add_to(mapa)
    if geometrija_za_crtanje is not None:
        Draw(
            export=False,
            draw_options={
                "polyline": False,
                "rectangle": False,
                "circle": False,
                "circlemarker": False,
                "marker": geometrija_za_crtanje == "Point",
                "polygon": (
                    {"allowIntersection": False, "showArea": True}
                    if geometrija_za_crtanje == "Polygon"
                    else False
                ),
            },
            edit_options={"edit": True, "remove": True},
        ).add_to(mapa)
    folium.LayerControl(position="topright", collapsed=False).add_to(mapa)
    mapa.fit_bounds([[min_y, min_x], [max_y, max_x]])
    return mapa


def ucitaj_zone() -> dict[int, str]:
    """Vrati ID i naziv svake zone za CRUD padajuce liste."""

    zone = prikazi_sve("zone_kampusa")
    return dict(zip(zone["zona_id"], zone["naziv"], strict=True))


def polje_za_vrednost(kolona: str, kljuc: str, pocetna_vrednost=None):
    """Prikazi odgovarajuci unos za izabranu SQL kolonu."""

    if kolona == "zona_id":
        zone = ucitaj_zone()
        id_vrednosti = list(zone)
        indeks = id_vrednosti.index(int(pocetna_vrednost)) if pocetna_vrednost else 0
        return st.selectbox(
            "Zona",
            id_vrednosti,
            index=indeks,
            format_func=lambda zona_id: f"{zona_id} - {zone[zona_id]}",
            key=kljuc,
        )
    if kolona == "tip" and "parkiralista" in kljuc:
        opcije = ["javno", "privatno"]
        indeks = opcije.index(pocetna_vrednost) if pocetna_vrednost in opcije else 0
        return st.selectbox("Tip", opcije, index=indeks, key=kljuc)
    if kolona == "stanje":
        opcije = ["ispravno", "neispravno"]
        indeks = opcije.index(pocetna_vrednost) if pocetna_vrednost in opcije else 0
        return st.selectbox("Stanje", opcije, index=indeks, key=kljuc)

    return st.text_input(
        kolona.replace("_", " ").capitalize(),
        value="" if pocetna_vrednost is None else str(pocetna_vrednost),
        key=kljuc,
    )


def osvezi_podatke() -> None:
    """Ocisti kes nakon CRUD izmene da mapa odmah prikaze novo stanje."""

    ucitaj_postgis_sloj.clear()


def procitaj_izbor_sa_mape(sadrzaj: str | None) -> dict | None:
    """Procitaj naziv tabele i ID iz sadrzaja kliknutog objekta."""

    if not sadrzaj:
        return None
    poklapanje = re.search(r"GIS_IZBOR:([a-z_]+):(\d+)", sadrzaj)
    if poklapanje is None:
        return None
    return {
        "tabela": poklapanje.group(1),
        "id": int(poklapanje.group(2)),
    }


def stil_izabranog_reda(red, tabela: str, id_kolona: str):
    """Istakni red koji odgovara trenutno izabranom objektu."""

    izabrani = st.session_state.get("izabrani_objekat")
    if (
        izabrani is not None
        and izabrani["tabela"] == tabela
        and int(red[id_kolona]) == izabrani["id"]
    ):
        return [
            "background-color: #ffff00; color: #111111; font-weight: 700"
            for _ in red
        ]
    return ["" for _ in red]


def prikazi_crud() -> dict:
    """Prikazi CRUD kontrole i vrati trenutno stanje izabrane operacije."""

    st.subheader("Upravljanje podacima")
    if st.session_state.pop("prikazi_tabelu_nakon_dodavanja", False):
        st.session_state["crud_operacija"] = "Prikaz"
    poruka = st.session_state.pop("crud_poruka", None)
    if poruka:
        st.success(poruka)

    naziv_tabele = st.selectbox("Tabela", list(CRUD_TABELE), key="crud_tabela")
    operacija = st.segmented_control(
        "Operacija",
        ["Prikaz", "Dodaj", "Izmeni", "Obrisi"],
        default="Prikaz",
        key="crud_operacija",
    )
    konfiguracija = CRUD_TABELE[naziv_tabele]
    tabela = konfiguracija["tabela"]
    id_kolona = konfiguracija["id"]
    podaci = prikazi_sve(tabela)
    stanje = {
        "operacija": operacija,
        "naziv_tabele": naziv_tabele,
        "tabela": tabela,
        "konfiguracija": konfiguracija,
    }

    if operacija == "Prikaz":
        kolone = [kolona for kolona in podaci.columns if kolona != "geometrija"]
        prikaz = podaci[kolone].reset_index(drop=True)
        stilizovan_prikaz = prikaz.style.apply(
            stil_izabranog_reda,
            axis=1,
            tabela=tabela,
            id_kolona=id_kolona,
        )
        izabrani = st.session_state.get("izabrani_objekat")
        podrazumevani_redovi = []
        if izabrani is not None and izabrani["tabela"] == tabela:
            indeksi = prikaz.index[prikaz[id_kolona] == izabrani["id"]].tolist()
            podrazumevani_redovi = indeksi[:1]
        oznaka_izbora = (
            str(izabrani["id"])
            if izabrani is not None and izabrani["tabela"] == tabela
            else "bez"
        )
        dogadjaj = st.dataframe(
            stilizovan_prikaz,
            hide_index=True,
            height=260,
            on_select="rerun",
            selection_mode="single-row",
            selection_default={"selection": {"rows": podrazumevani_redovi}},
            key=f"crud_prikaz_{tabela}_{oznaka_izbora}",
        )
        izabrani_redovi = tuple(dogadjaj.selection.rows)
        if izabrani_redovi:
            red = prikaz.iloc[izabrani_redovi[0]]
            novi_izbor = {
                "tabela": tabela,
                "id": int(red[id_kolona]),
            }
            if novi_izbor != izabrani:
                st.session_state["izabrani_objekat"] = novi_izbor
                st.rerun()
        elif izabrani is not None and izabrani["tabela"] == tabela:
            st.session_state.pop("izabrani_objekat", None)
            st.rerun()
        return stanje

    if operacija == "Dodaj":
        st.caption("Sve vrednosti su obavezne.")
        novi_podaci = {
            kolona: polje_za_vrednost(kolona, f"dodaj_{tabela}_{kolona}")
            for kolona in konfiguracija["kolone"]
        }
        atributi_popunjeni = all(
            vrednost is not None
            and (not isinstance(vrednost, str) or bool(vrednost.strip()))
            for vrednost in novi_podaci.values()
        )
        kljuc_geometrije = f"nova_geometrija_{tabela}"
        if kljuc_geometrije in st.session_state:
            st.success("Geometrija je nacrtana.")
        else:
            st.info("Nacrtaj geometriju na mapi.")
        stanje.update(
            {
                "novi_podaci": novi_podaci,
                "atributi_popunjeni": atributi_popunjeni,
                "kljuc_geometrije": kljuc_geometrije,
            }
        )
        return stanje

    if podaci.empty:
        st.info("Izabrana tabela nema redove.")
        return stanje

    redovi_po_id = podaci.set_index(id_kolona)
    izabrani_id = st.selectbox(
        "Red",
        redovi_po_id.index.tolist(),
        format_func=lambda red_id: f"ID {red_id}",
        key=f"crud_red_{tabela}",
    )

    if operacija == "Izmeni":
        kolona = st.selectbox(
            "Kolona",
            konfiguracija["kolone"],
            key=f"crud_kolona_{tabela}",
        )
        trenutna_vrednost = redovi_po_id.loc[izabrani_id, kolona]
        with st.form(f"izmeni_{tabela}_{kolona}"):
            nova_vrednost = polje_za_vrednost(
                kolona,
                f"izmeni_{tabela}_{kolona}",
                trenutna_vrednost,
            )
            potvrda = st.form_submit_button(
                "Sacuvaj izmenu", type="primary", icon=":material/save:"
            )
        if potvrda:
            try:
                azuriraj_red(tabela, int(izabrani_id), {kolona: nova_vrednost})
                osvezi_podatke()
                st.success("Red je izmenjen.")
            except (ValueError, PostgreSQLError) as greska:
                st.error(f"Red nije izmenjen: {greska}")
        return stanje

    st.warning(f"Bice obrisan red sa ID {izabrani_id}.")
    potvrda_brisanja = st.checkbox("Potvrdjujem brisanje")
    if st.button(
        "Obrisi red",
        disabled=not potvrda_brisanja,
        icon=":material/delete:",
    ):
        try:
            obrisi_red(tabela, int(izabrani_id))
            osvezi_podatke()
            st.success("Red je obrisan.")
        except (ValueError, PostgreSQLError) as greska:
            st.error(f"Red nije obrisan: {greska}")

    return stanje


with st.sidebar:
    st.header("GisCampus")
    crud_stanje = prikazi_crud()
    if crud_stanje["operacija"] != "Dodaj":
        st.divider()
        st.subheader("Prostorne analize")
        izabrana_analiza = st.selectbox(
            "Analiza",
            list(ANALIZE),
            key="izabrana_prostorna_analiza",
        )
    else:
        izabrana_analiza = "Bez analize"

st.title("GisCampus")
rezultat_analize = pokreni_analizu(izabrana_analiza)

if crud_stanje["operacija"] == "Dodaj":
    konfiguracija = crud_stanje["konfiguracija"]
    tabela = crud_stanje["tabela"]
    st.subheader(f"Dodavanje: {crud_stanje['naziv_tabele']}")
    st.write(
        "Popuni obavezne atribute u bocnoj traci, a zatim nacrtaj "
        "objekat na mapi."
    )
    postojeca_geometrija = st.session_state.get(crud_stanje["kljuc_geometrije"])
    rezultat_mape = st_folium(
        napravi_mapu(
            geometrija_za_crtanje=konfiguracija["geometrija"],
            sacuvana_geometrija=postojeca_geometrija,
        ),
        width=1000,
        height=560,
        key=f"dodavanje_geometrije_{tabela}",
        returned_objects=["all_drawings"],
    )
    crtezi = rezultat_mape.get("all_drawings")
    if crtezi:
        nacrtana = shape(crtezi[-1]["geometry"])
        if nacrtana.geom_type != konfiguracija["geometrija"]:
            st.error(f"Potrebno je nacrtati geometriju {konfiguracija['geometrija']}.")
            st.session_state.pop(crud_stanje["kljuc_geometrije"], None)
        elif not nacrtana.is_valid:
            st.error("Nacrtana geometrija nije ispravna.")
            st.session_state.pop(crud_stanje["kljuc_geometrije"], None)
        else:
            geometrija_m = gpd.GeoSeries([nacrtana], crs=4326).to_crs(32634).iloc[0]
            st.session_state[crud_stanje["kljuc_geometrije"]] = geometrija_m

    geometrija = st.session_state.get(crud_stanje["kljuc_geometrije"])
    zona_je_ispravna = True
    if geometrija is not None:
        if konfiguracija["ima_povrsinu"]:
            st.metric("Automatski izracunata povrsina", f"{geometrija.area:.2f} m2")
        else:
            st.success("Tacka infrastrukturnog objekta je spremna.")
        if tabela != "zone_kampusa":
            try:
                zona_id, naziv_zone = pronadji_zonu_za_geometriju(geometrija)
                st.success(f"Automatski dodeljena zona: {naziv_zone} (ID {zona_id}).")
            except ValueError as greska:
                zona_je_ispravna = False
                st.error(str(greska))

    spremno_za_upis = (
        crud_stanje["atributi_popunjeni"]
        and geometrija is not None
        and zona_je_ispravna
    )
    if st.button(
        "Dodaj objekat u bazu",
        type="primary",
        icon=":material/add_location_alt:",
        disabled=not spremno_za_upis,
    ):
        try:
            novi_id = dodaj_prostorni_red(
                tabela,
                crud_stanje["novi_podaci"],
                geometrija,
            )
            st.session_state.pop(crud_stanje["kljuc_geometrije"], None)
            osvezi_podatke()
            pokreni_analizu.clear()
            st.session_state["crud_poruka"] = f"Dodat je objekat sa ID {novi_id}."
            st.session_state["prikazi_tabelu_nakon_dodavanja"] = True
            st.rerun()
        except (ValueError, PostgreSQLError) as greska:
            st.error(f"Objekat nije dodat: {greska}")
else:
    izabrani_objekat = st.session_state.get("izabrani_objekat")
    rezultat_mape = st_folium(
        napravi_mapu(
            izabrana_analiza,
            rezultat_analize,
            izabrani_objekat=izabrani_objekat,
        ),
        width=1000,
        height=560,
        key="gis_kampus_mapa",
        returned_objects=[
            "last_object_clicked_popup",
            "last_object_clicked_count",
        ],
    )
    broj_klika = rezultat_mape.get("last_object_clicked_count")
    prethodni_broj_klika = st.session_state.get("poslednji_broj_klika_na_mapi")
    if broj_klika is not None and broj_klika != prethodni_broj_klika:
        st.session_state["poslednji_broj_klika_na_mapi"] = broj_klika
        izbor_sa_mape = procitaj_izbor_sa_mape(
            rezultat_mape.get("last_object_clicked_popup")
        )
        if izbor_sa_mape is not None and izbor_sa_mape != izabrani_objekat:
            st.session_state["izabrani_objekat"] = izbor_sa_mape
            st.rerun()

if crud_stanje["operacija"] != "Dodaj" and izabrana_analiza != "Bez analize":
    st.subheader("Rezultat prostorne analize")
    if rezultat_analize.empty:
        st.info("Analiza je uspesno izvrsena, ali nije pronadjen nijedan rezultat.")
    else:
        kolone = [
            kolona
            for kolona in rezultat_analize.columns
            if kolona not in {rezultat_analize.geometry.name, "index_right"}
        ]
        st.dataframe(rezultat_analize[kolone], hide_index=True)
