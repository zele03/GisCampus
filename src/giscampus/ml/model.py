"""Ucitavanje istreniranog U-Net modela za segmentaciju zgrada."""

from pathlib import Path

import segmentation_models_pytorch as smp
import torch
from torch import nn

KOREN_PROJEKTA = Path(__file__).resolve().parents[3]
FOLDER_MODELA = KOREN_PROJEKTA / "data" / "ml" / "models"
NAZIV_MODELA = "unet_bldg_instance.pth"
PUTANJA_MODELA = FOLDER_MODELA / NAZIV_MODELA
URL_MODELA = (
    "https://hf.co/nilsho01/unet-resnet34-vhr-buildings/resolve/main/"
    "unet_bldg_instance.pth"
)

VELICINA_ISECKA = 256
BROJ_ULAZNIH_KANALA = 3
BROJ_IZLAZNIH_KANALA = 3
ENKODER = "resnet34"
BROJ_NIVOA = 5
KANALI_DEKODERA = (256, 128, 64, 32, 16)


def napravi_unet() -> nn.Module:
    """Napravi arhitekturu koja tacno odgovara istreniranim tezinama."""

    return smp.Unet(
        encoder_name=ENKODER,
        encoder_depth=BROJ_NIVOA,
        encoder_weights=None,
        decoder_channels=KANALI_DEKODERA,
        decoder_use_norm="batchnorm",
        decoder_attention_type=None,
        decoder_interpolation="nearest",
        in_channels=BROJ_ULAZNIH_KANALA,
        classes=BROJ_IZLAZNIH_KANALA,
        activation=None,
        aux_params=None,
    )


def preuzmi_tezine() -> Path:
    """Preuzmi istrenirane tezine ako vec nisu sacuvane lokalno."""

    FOLDER_MODELA.mkdir(parents=True, exist_ok=True)
    torch.hub.load_state_dict_from_url(
        URL_MODELA,
        model_dir=str(FOLDER_MODELA),
        file_name=NAZIV_MODELA,
        map_location="cpu",
        progress=True,
        weights_only=True,
    )
    return PUTANJA_MODELA


def ucitaj_istrenirani_unet(uredjaj: str = "cpu") -> nn.Module:
    """Ucitaj arhitekturu i istrenirane parametre, pa ukljuci rezim detekcije."""

    putanja = preuzmi_tezine()
    model = napravi_unet()
    stanje = torch.load(
        putanja,
        map_location=uredjaj,
        weights_only=True,
    )
    model.load_state_dict(stanje)
    model.to(uredjaj)
    model.eval()
    return model
