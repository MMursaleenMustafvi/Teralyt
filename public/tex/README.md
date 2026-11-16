# Photo textures

Photo textures used by the 3D society model (`src/map/models3d.js`, `usePhoto`). They come from [ambientCG](https://ambientcg.com) and
[Poly Haven](https://polyhaven.com) and are released under **CC0 1.0** (public domain, no attribution required; credited here anyway).

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
| `foliage.webp` | Poly Haven `jacaranda_tree` (compound leaves), Poly Haven `island_tree_02` (single leaves), ambientCG Bark014 | trees: leaf clusters for round crowns (neem, sheesham) and columnar crowns (Ashoka), a date-palm frond, bark; made by `tools/make_foliage.py` |

Each file is the asset's 1K colour map scaled to 512 px. Large stains are removed with a high-pass filter on the tiled image (so the file still
tiles) and the fine grain is strengthened for asphalt and plaster. `tools/make_textures.py` rebuilds them.

The map tints each photo so that its average colour matches the colour the map already used, so the palette and legend stay the same. If these
files cannot be loaded, the drawn (canvas) textures are used instead.
