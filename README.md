# mrxs-truncate

Drop the top of a MIRAX (`.mrxs`) pyramid to build an archive tier.
**No re-encoding, no metadata rewrite, remaining levels stay bit-identical.**

On a routine placental slide collection, dropping level 0 recovers **~70 % of the bytes**
— and costs essentially nothing, because level 0 turns out to be empty magnification.

```bash
python mrxs_truncate.py slide.mrxs --drop 1              # keep ~0.35 µm/px
python mrxs_truncate.py /path/to/case/ --drop 1 --drop 2 # whole folder, both tiers
python mrxs_truncate.py slide.mrxs --drop 1 --dry-run
```

Requires Python 3 and [OpenSlide](https://openslide.org/) (`openslide-python`).

---

## Why it works

In MIRAX, **each pyramid level lives in its own `Data*.dat` file.** Measured on one slide:

| file | 750 MB | 224 MB | 67 MB | 20 MB | 5.8 MB | … |
|---|---|---|---|---|---|---|
| level | 0 | 1 | 2 | 3 | 4 | … |

The ratio is ~3.3× rather than 4× (JPEG compresses slightly worse after downsampling).
`Data0001.dat` holds **level 0 and nothing else** — 750 MB out of 1.07 GB.

So the whole operation is:

```bash
rm slide/Data0001.dat
```

The slide still opens, `level_count` still reports 10, `mpp` is correct, the thumbnail works,
and levels 1→9 are **bit-identical** to the original (verified by md5 of `read_region` output).
Neither `Slidedat.ini` nor `Index.dat` needs to be touched.

Because there is **no re-encoding**, colours remain exactly what the scanner produced. That
matters if your archive's purpose is to serve as a colour reference later.

## What it costs: nothing measurable

Power spectrum of 47 tiles of 512 px at level 0: only **1.7 %** of the energy lies above the
Nyquist frequency of level 1. The scanner samples at 0.177 µm/px, but the optics deliver
nothing beyond ~0.35 µm/px. **Level 0 is empty magnification** — the 70 % is free, not a
trade-off.

Corollary worth knowing even if you never truncate anything: embedding at 20× (0.5 µm/px)
loses nothing either, and a cell-level probe will not gain detail by reading level 0. The
ceiling is optical, not a matter of sampling.

## Measured gains

Over 120 slides / 166 GB (level 0 at 0.177 µm/px):

| target kept | dropped | 100 GB becomes | gain | p10–p90 |
|---|---|---|---|---|
| 0.353 µm/px | level 0 | 30 GB | **−69.6 %** | 69–73 % |
| 0.706 µm/px | levels 0 and 1 | 8.6 GB | **−91.4 %** | 91–92 % |

The spread is tight, so the figure holds slide by slide, not just on average.

---

## Caveats — read these before deleting anything

**1. Check your reader first.** OpenSlide opens the pyramid *lazily*, level by level, so a
truncated slide opens and displays fine. A MIRAX reader that **indexes every `Data*.dat` at
open time** — a common design for building a tile index — will fail at `open()`, even though
the missing level would never be read. We hit exactly this with an in-house native reader:
`Cannot open Data0001.dat`, and the whole downstream pipeline was dead. **Test opening before
you delete.**

**2. The absent level is still announced.** OpenSlide keeps reporting `level_count = 10`.
Requesting the missing level raises an error that **locks the handle** — subsequent reads fail
even when valid, and you must reopen. Consumers should target a **µm/px value, never a level
index**.

**3. Multi-focal scans.** ~1 % of slides are scanned at several focal planes and carry **two
pyramids side by side**: `Data0001` and `Data0011` are the same size. A blind
`rm Data0001.dat` recovers only half. This script identifies level 0 **by size** — the two
largest files within 20 % of each other means a duplicated pyramid — never by name.

**4. Do not rewrite `Slidedat.ini`.** The obvious idea — re-declaring 9 levels via
`HIER_0_COUNT`, shifting `HIER_0_VAL_n` and the `LAYER_0_LEVEL_n` sections — makes OpenSlide
refuse to open the slide: `y (411) not correct multiple for zoom level (0)`. `Index.dat`
validates tile positions against the level number, so it would need a binary patch. Declaring
nothing already works.

**5. Testing trap.** Outside tissue, level 0 **still answers**: OpenSlide fills with the
background colour without opening any `Data*.dat`. Probe at the **centre** of the slide, or
you will wrongly conclude the truncation changed nothing.

**6. Deep Zoom degrades at maximum zoom**, since it derives from level 0. Have the missing
level return 404 so OpenSeadragon falls back to the parent level. Correct behaviour for an
archive-preview tier; not for a working tier.

## Annotations are unaffected

Since `Slidedat.ini` is untouched, the coordinate frame is unchanged:
`bounds-x/y/width/height`, `level_dimensions[0]` and `mpp` are identical across the original
and both truncated tiers.

Verified on 287 annotations of one slide: 256 px tiles read at annotation centroids give the
same md5 on the original, at 0.353 µm/px and at 0.706 µm/px, across levels 1, 2 and 3.
GeoJSON annotations, superpixel caches and heatmaps all survive as-is — **provided you
truncate in place** (an `rm`) rather than copying under a new name, which would fork the
slide's identity and orphan its artefacts.

## What the script adds over `rm`

- finds level 0 **by size**, handling multi-focal scans;
- refuses to act if the targeted levels weigh less than 50 % of the total (suspicious detection);
- derives the `_x28` / `_x14` suffix from the resulting µm/px;
- **verifies by md5 that the remaining levels are bit-identical** to the original before
  returning.

It copies rather than deletes, so you can validate on real data first. In production you would
delete in place: the cost is then that of an `rm`, independent of slide size.

## Status

Measured on a placental pathology collection (MIRAX, 0.177 µm/px). The numbers
above are from that collection; the mechanism is generic, the ratios may differ on other
scanners. Not deployed at scale here — there is still years of disk headroom, and the native
format is kept while it fits.

## Licence

MIT — see [LICENSE](LICENSE).
