"""GisCampus aplikacija za pregled slojeva i CRUD rad sa podacima."""

from warnings import catch_warnings, simplefilter

import folium
import geopandas as gpd
import streamlit as st
from branca.element import MacroElement, Template
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
from src.giscampus.sql.crud import azuriraj_red, dodaj_red, obrisi_red, prikazi_sve
from src.giscampus.sql.database import povezi_se

st.set_page_config(page_title="GisCampus", page_icon=":material/map:", layout="wide")

SLOJEVI = {
    "Zone kampusa": {
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
    },
    "Zgrade": {
        "tabela": "zgrade",
        "id": "zgrada_id",
        "kolone": ["zona_id", "naziv", "tip"],
    },
    "Parkiralista": {
        "tabela": "parkiralista",
        "id": "parkiraliste_id",
        "kolone": ["zona_id", "naziv", "tip"],
    },
    "Zelene povrsine": {
        "tabela": "zelene_povrsine",
        "id": "zelena_povrsina_id",
        "kolone": ["zona_id", "tip"],
    },
    "Infrastrukturni objekti": {
        "tabela": "infrastrukturni_objekti",
        "id": "infrastrukturni_objekat_id",
        "kolone": ["zona_id", "naziv", "stanje"],
    },
    "Tereni": {
        "tabela": "tereni",
        "id": "teren_id",
        "kolone": ["zona_id", "naziv"],
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
) -> dict[str, folium.GeoJson]:
    """Dodaj PostGIS slojeve i odredi njihovu pocetnu vidljivost."""

    folium_slojevi = {}
    for naziv, konfiguracija in SLOJEVI.items():
        podaci = ucitaj_postgis_sloj(naziv)
        boja = konfiguracija["boja"]
        opcije = {
            "name": naziv,
            "show": prikazi_slojeve,
            "style_function": lambda _, boja=boja: {
                "color": boja,
                "weight": 3,
                "fillColor": boja,
                "fillOpacity": 0.25,
            },
            "tooltip": folium.GeoJsonTooltip(
                fields=konfiguracija["polja"],
                aliases=konfiguracija["nazivi_polja"],
            ),
        }
        if konfiguracija["geometrija"] == "Point":
            opcije["marker"] = folium.CircleMarker(radius=7)

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
                "providnost": 0.25,
                "debljina": 3,
            }
            for naziv in slojevi
        }


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
) -> folium.Map:
    """Napravi zavrsnu mapu sa rasterom i svim PostGIS slojevima."""

    min_x, min_y, max_x, max_y = OKVIR_KAMPUSA
    mapa = folium.Map(
        location=[(min_y + max_y) / 2, (min_x + max_x) / 2],
        zoom_start=16,
        tiles=None,
        control_scale=False,
    )
    _dodaj_raster(mapa, preuzmi_raster_kampusa())
    prikazi_osnovne_slojeve = naziv_analize == "Bez analize"
    slojevi = dodaj_postgis_slojeve(mapa, prikazi_osnovne_slojeve)
    KontrolaSimbologije(slojevi).add_to(mapa)
    if rezultat_analize is not None:
        dodaj_rezultat_analize(mapa, naziv_analize, rezultat_analize)
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


def prikazi_crud() -> None:
    """Prikazi CRUD kontrole za sve projektne tabele u bocnoj traci."""

    st.subheader("Upravljanje podacima")
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

    if operacija == "Prikaz":
        kolone = [kolona for kolona in podaci.columns if kolona != "geometrija"]
        st.dataframe(podaci[kolone], hide_index=True, height=260)
        return

    if operacija == "Dodaj":
        with st.form(f"dodaj_{tabela}"):
            novi_podaci = {
                kolona: polje_za_vrednost(kolona, f"dodaj_{tabela}_{kolona}")
                for kolona in konfiguracija["kolone"]
            }
            potvrda = st.form_submit_button(
                "Dodaj red", type="primary", icon=":material/add:"
            )
        if potvrda:
            try:
                novi_id = dodaj_red(tabela, novi_podaci)
                osvezi_podatke()
                st.success(f"Dodat je red sa ID {novi_id}.")
            except Exception as greska:
                st.error(f"Red nije dodat: {greska}")
        return

    if podaci.empty:
        st.info("Izabrana tabela nema redove.")
        return

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
            except Exception as greska:
                st.error(f"Red nije izmenjen: {greska}")
        return

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
        except Exception as greska:
            st.error(f"Red nije obrisan: {greska}")


with st.sidebar:
    st.header("GisCampus")
    prikazi_crud()
    st.divider()
    st.subheader("Prostorne analize")
    izabrana_analiza = st.selectbox(
        "Analiza",
        list(ANALIZE),
        key="izabrana_prostorna_analiza",
    )

st.title("GisCampus")
rezultat_analize = pokreni_analizu(izabrana_analiza)
st_folium(
    napravi_mapu(izabrana_analiza, rezultat_analize),
    width=1000,
    height=560,
    key="gis_kampus_mapa",
    returned_objects=[],
)

if izabrana_analiza != "Bez analize":
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
