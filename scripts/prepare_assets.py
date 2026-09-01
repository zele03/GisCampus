"""Preuzimanje lokalnog rastera i, po potrebi, težina ML modela."""

import argparse
import sys
from pathlib import Path

KOREN = Path(__file__).resolve().parents[1]
if str(KOREN) not in sys.path:
    sys.path.insert(0, str(KOREN))

from src.giscampus.geo.data import preuzmi_raster_kampusa


def main() -> None:
    parser = argparse.ArgumentParser(description="Pripremi velike lokalne fajlove.")
    parser.add_argument(
        "--with-model",
        action="store_true",
        help="Preuzmi i težine ML modela, potrebne samo za novu detekciju.",
    )
    args = parser.parse_args()
    raster = preuzmi_raster_kampusa()
    print(f"Rasterska podloga je spremna: {raster.relative_to(KOREN)}")
    if args.with_model:
        from src.giscampus.ml.model import preuzmi_tezine

        model = preuzmi_tezine()
        print(f"Težine modela su spremne: {model.relative_to(KOREN)}")


if __name__ == "__main__":
    main()
