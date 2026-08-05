#!/usr/bin/env python3
"""Copie une lame MRXS en jetant le haut de la pyramide — pour un tier archive.

Chaque niveau de zoom MIRAX vit dans SON PROPRE Data*.dat (ratio ~3,3× entre niveaux).
Ne pas copier le fichier du niveau 0 suffit : ni Slidedat.ini ni Index.dat n'ont besoin
d'être touchés, la lame s'ouvre et les niveaux restants sortent bit-identiques. Réécrire
l'ini pour re-déclarer les niveaux, au contraire, casse l'ouverture (Index.dat valide les
positions de tuiles contre le numéro de niveau).

Le niveau 0 reste ANNONCÉ par OpenSlide : le demander lève une erreur qui verrouille le
handle. Un consommateur doit viser un mpp, pas un numéro de niveau. Le DeepZoom du viewer
casse donc au zoom maximal — c'est le prix d'un tier « mieux qu'un thumbnail ».

Usage : python mrxs_truncate.py <lame.mrxs|dossier_cas> --drop 1 [--drop 2] [--dry-run]
"""
import argparse
import hashlib
import shutil
import time
from pathlib import Path

import openslide


def pyramid_files(src: Path):
    """[[fichiers du niveau 0], [niveau 1], ...] par taille décroissante.

    Les scans multi-plans de focale (1 % des lames) portent DEUX pyramides côte à côte :
    Data0001 et Data0011 font la même taille. D'où le repérage par TAILLE et non par nom,
    qu'un `rm Data0001.dat` aveugle raterait à moitié.
    """
    fs = sorted(src.glob("Data*.dat"), key=lambda p: -p.stat().st_size)
    k = 2 if len(fs) > 1 and fs[1].stat().st_size > 0.8 * fs[0].stat().st_size else 1
    return [fs[i:i + k] for i in range(0, len(fs), k)]


def truncate(mrxs: Path, drop: int, dry_run=False):
    src = mrxs.with_suffix("")
    lv = pyramid_files(src)
    total = sum(p.stat().st_size for p in src.glob("Data*.dat"))
    jetes = [p for grp in lv[:drop] for p in grp]
    poids = sum(p.stat().st_size for p in jetes)
    if poids < 0.5 * total:
        raise SystemExit(f"{mrxs.name} : les {drop} premiers niveaux ne pèsent que "
                         f"{poids / total:.0%} — repérage douteux, on ne touche à rien")

    with openslide.OpenSlide(str(mrxs)) as s:
        mpp = float(s.properties["openslide.mpp-x"]) * 2 ** drop
        dims = s.level_dimensions
    tag = f"x{round(10 / mpp)}"                       # x40 ↔ 0,25 µm/px par convention
    dst = src.with_name(f"{src.name}_{tag}")
    if dst == src:
        raise SystemExit("destination = source, refus")
    print(f"{mrxs.name} → {dst.name}  ({total / 1e9:.2f} Go, jette {poids / 1e9:.2f} Go "
          f"= {poids / total:.0%}, reste {mpp:.3f} µm/px)")
    if dry_run:
        return 0.0, 0, 0

    t0 = time.time()
    dst.mkdir(exist_ok=True)
    garde = set(src.iterdir()) - set(jetes)
    for f in garde:
        shutil.copy2(f, dst / f.name)
    shutil.copy2(mrxs, dst.with_suffix(".mrxs"))
    dt = time.time() - t0

    # vérification : les niveaux gardés doivent être BIT-IDENTIQUES à l'original
    # Slidedat.ini étant intact, la NUMÉROTATION des niveaux ne décale pas : le niveau i de
    # la copie est le niveau i de l'original, seuls les `drop` premiers sont devenus illisibles.
    def md5s(path, levels):
        out = {}
        with openslide.OpenSlide(str(path)) as s:
            for i in levels:
                w, h = s.level_dimensions[i]
                d = int(s.level_downsamples[i])
                im = s.read_region(((w // 2 - 128) * d, (h // 2 - 128) * d), i, (256, 256))
                out[i] = hashlib.md5(im.convert("RGB").tobytes()).hexdigest()
        return out
    restants = range(drop, len(dims))
    ref = md5s(mrxs, restants)
    got = md5s(dst.with_suffix(".mrxs"), restants)
    if ref != got:
        raise SystemExit(f"{dst.name} : niveaux NON identiques, copie suspecte")
    neuf = sum(p.stat().st_size for p in dst.rglob("*"))
    print(f"  {dt:5.1f} s | {neuf / 1e9:.2f} Go | {len(ref)} niveaux vérifiés identiques")
    return dt, poids, neuf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cible", help="une lame .mrxs ou un dossier de cas")
    ap.add_argument("--drop", type=int, action="append", required=True,
                    help="nb de niveaux du haut à jeter (1 = x28, 2 = x14) ; répétable")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    p = Path(a.cible)
    lames = sorted(p.glob("*.mrxs")) if p.is_dir() else [p]
    lames = [m for m in lames if m.with_suffix("").is_dir() and "_x" not in m.stem]
    print(f"{len(lames)} lame(s)\n")
    t = gagne = neuf = 0.0
    for m in lames:
        for d in a.drop:
            dt, g, nf = truncate(m, d, a.dry_run)
            t += dt; gagne += g; neuf += nf
    if not a.dry_run:
        print(f"\ntotal : {t:.1f} s, {gagne / 1e9:.2f} Go non copiés, "
              f"{neuf / 1e9:.2f} Go écrits ({t / max(len(lames), 1):.1f} s/lame)")


if __name__ == "__main__":
    main()
