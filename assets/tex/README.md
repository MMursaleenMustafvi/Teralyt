# Photo textures

Tileable photo textures used by the 3D society model (`assets/models3d.js`, `usePhoto`). All come from
[ambientCG](https://ambientcg.com) and are released under **CC0 1.0** (public domain, no attribution required; credited here anyway).

| File | ambientCG asset | Used for |
| --- | --- | --- |
| `asphalt.jpg` | Asphalt025C | roads |
| `grass.jpg` | Grass004 | society ground, lawns, parks, verges |
| `soil.jpg` | Ground103 | vacant land, plots, dirt |
| `plaster.jpg` | Plaster001 | house and building walls, boundary walls, parapets |
| `brick.jpg` | Bricks101 | brick facades, brick cladding |
| `paving.jpg` | PavingStones070 | footpaths, paved strips, plinths, stone cladding |
| `concrete.jpg` | Concrete036 | flat roofs, floor slabs |
| `gravel.jpg` | Gravel023 | gravel areas |

Each file is the asset's 1K colour map scaled to 512 px. Large stains are removed with a high-pass filter on the tiled image (so the file still
tiles) and the fine grain is strengthened for asphalt and plaster. `tools/make_textures.py` rebuilds them.

The map tints each photo so that its average colour matches the colour the map already used, so the palette and legend stay the same. If these
files cannot be loaded, the drawn (canvas) textures are used instead.
