# Terralyt 3D map: handover

Updated 14 November 2026, on branch `feature/3d-map`. The commit that contains this file is the current state. Earlier states: `d2884cf` (before the plots were read from the block maps), `206b1f4` (first version with official plots, the gate and houses; it had zig-zag streets and odd plot shapes, fixed since).

This file is for whoever continues the 3D map work in a new chat, with no access to the earlier conversation. It says what exists, how it was built, what has been checked, and what is still wrong or unverified. Read it together with `CLAUDE.md` in the same folder, which holds the project rules and the code reference. Where the two disagree, trust this file for the current state and `CLAUDE.md` for the rules.

## 1. The project in short

Terralyt is a Final Year Project at FAST-NUCES (Chiniot-Faisalabad), 2026. It shows a Pakistani housing society as an interactive 3D map, rates its development Low / Medium / High, and gives a 5-year forecast. The pilot society is **FDA City, Faisalabad** (about 31.522 N, 73.086 E).

- **Taha Saleem Sheikh** owns the 3D map and the AI/ML model. This handover covers only the 3D map.
- **Muhammad Mursaleen Mustafvi** owns the web UI and the GitHub repo.
- **Rahmeen Nasr** is the third team member. Supervisor: Ms. Mahzaib Younas.

## 2. What Taha wants (read this before changing anything)

These rules came from repeated corrections. Earlier work was rejected each time one of them was broken.

1. **Satellite imagery is only for measuring real things:** the nalla (storm drain), roads, roundabouts, their widths, the society boundary, and (since this session, at his request) which plots have a house on them.
2. **Everything else comes from the official FDA City maps:** which site is a school, mosque or park, the block layout, the plots, official road widths, areas. No assumptions and no invented facilities.
3. **The result is a clean, realistic, detailed, interactive 3D model.** It is not a satellite photo with boxes on top. The drawn ground is the default; the satellite photo is an optional toggle.
4. **Plots are land parcels, not buildings.** A house is drawn only where a building stands today.
5. **A school must look like and be labelled as a school, a mosque as a mosque,** and so on.
6. **Technology:** three.js for the detailed society model, combined with CesiumJS for the real-world view.
7. **Audit before reporting.** Check the work, then state plainly what is verified and what is not.

How Taha likes to work: plain language, short answers, no unrequested features, few questions. He has given blanket permission to install tools, download files and use the internet. He often asks for the run command. He wants each finished step pushed to the GitHub branch.

Official maps he supplied:

- Overall plan and block index: https://fdacity.pk/map_fda.php
- Blocks B to E: https://fdacity.pk/map_fda_b.html, `..._c.html`, `..._d.html`, `..._e.html`
- Block F: https://fdacity.pk/images/fdacity/map-block-f/fdacity_map-f1.jpg
- Second source for the overall plan: https://www.seerab.com/fda-city/
- The exact image URL of every sheet page is stored in `tools/source/plan_features.json` under `sheets`.

## 3. Hard project rules

- The UI is plain HTML, CSS and JavaScript. No React, no npm, no build step.
- Never commit to `main`. Work on `feature/3d-map`, push, open a pull request for Mursaleen. Do not merge your own pull request.
- Never commit `assets/config.js`, tokens or secrets. The Cesium ion token is pasted by Taha into `assets/config.js`, never into chat.
- Ask before changing any UI page other than `map.html`.
- Plot status comes from verified records only, never from imagery, and is shown with source and confidence. Until records exist the status is a sample value and says so.
- Building heights are assumed (3.5 m per storey) and must be labelled assumed.
- The 5-year forecast is always labelled as an estimate.
- There is no plot-comparison feature.

## 4. Current state

| Item | State |
| --- | --- |
| Repo on disk | `C:\Users\Taha\Teralyt` |
| GitHub | `MMursaleenMustafvi/Teralyt`, branch `feature/3d-map` |
| Pull request | Not opened yet |
| `main` | Untouched by this work |
| Cesium ion token | Not provided; the real-world tab has only been run with OpenStreetMap tiles and flat ground |

## 5. How to run

```powershell
cd C:\Users\Taha\Teralyt
python -m http.server 8000
```

Open `http://localhost:8000/map.html` and press Ctrl+F5. Opening the file directly does not work, because the page fetches GeoJSON and ES modules.

URL options: `?plot=B-12`, `?id=2500`, `?lm=121` (121 is the main gate), `?time=evening` or `?time=night`, `?ground=satellite`, `?view=earth`, `?audit=1`.

Machine quirks:

- `git` is at `C:\Program Files\Git\cmd` and may not be on PATH in a tool shell.
- Python 3.15 has shapely, numpy, pillow, matplotlib, playwright, opencv-python-headless, scikit-image, scipy and duckdb installed. Run the tools with `python -I`.
- `tools/shoot.py` takes headless screenshots with the installed Chrome and software rendering. Run one capture at a time. The page now loads in about 10 seconds.

## 6. What is built

`map.html` has two tabs.

**3D society model (three.js r169, default tab).** Ground, roads with lane markings and kerbs, roundabouts with monuments, the nalla with walls and bridges, the **main gate** on the Main Entrance Road, 11,014 plots, 120 named sites with 3D models, **355 houses standing today** (each built plot also has a boundary wall and gate), trees, street lights, moving cars, labels, a sky, shadows, day / **evening** / night light, an optional satellite photo ground, a mini-map and a compass. Controls: plot layers (real, development class, status, built/vacant, size), filters by size and status, block buttons A to F with block statistics, search, a guided tour, and a details panel when a plot or site is clicked.

**Real-world map (CesiumJS 1.119).** The same data on the globe. It loads only when its tab is opened.

| File | Lines | Role |
| --- | --- | --- |
| `map.html` | 171 | Page, controls, details panel, both tabs |
| `assets/society3d.js` | 1,183 | The three.js scene, houses, picking, layers, filters, tour, model audit |
| `assets/models3d.js` | 954 | Materials, textures, one model builder per site type, the gate and the house |
| `assets/map3d.js` | 336 | The CesiumJS view |
| `tools/trace_plots.py` | 461 | **New.** Reads plot outlines and streets off the six official block maps and registers each sheet to the real streets |
| `tools/make_data.py` | 1,540 | Generates every file in `data/` |
| `tools/trace_sheets.py` | 164 | Earlier digitisation of the named sites of Blocks B to F |
| `tools/audit.py` | 125 | Data audit |
| `tools/shoot.py` | 64 | Screenshot tool |
| `tools/source/plan_features.json` | | Named sites traced from the official maps, with control points |
| `tools/source/sheet_layout.json`, `sheet_ink_A..F.png`, `sheet_road_A..F.png` | | **New.** Output of `trace_plots.py`: plot cells, street centre lines, the drawn area and the street space of each sheet |
| `tools/source/buildings_fda.geojson` | | **New.** Building footprints around FDA City from Overture Maps (Google Open Buildings 2023 and Microsoft ML Buildings) |
| `tools/source/osm_fda_area.json` | | OpenStreetMap streets |
| `tools/source/nala_traced.geojson` | | Nalla traced on satellite imagery |
| `data/*.geojson` | | Generated output; `plots.geojson` is 7.4 MB, `buildings.geojson` is new |

The code reference (function names, data schema, performance rules) is in `CLAUDE.md`.

## 7. How the data was made

1. **Streets:** centrelines exported from OpenStreetMap (traced by its mappers on satellite imagery).
2. **Named sites:** each park, mosque, school and zone is a pixel box on its sheet in `plan_features.json`, with the kanal area printed on the map where there is one. Sheets are georeferenced by control points (roundabout centres and parks).
3. **Plots (new):** `trace_plots.py` downloads the six block maps, finds every small closed outline (a plot) by keeping only long straight lines, so that the printed plot numbers do not break the cells, and finds the white street corridors. It then **registers each sheet to the ground** by fitting the sheet's street centre lines to the OpenStreetMap streets (an affine fit, iterated). Fit quality: 1.9 to 3.0 m rms per sheet, and the median error in every part of every sheet is below about 2 m.
4. **Generation:** `make_data.py` splits the land into faces of the road network, carves each named site out to its official area (plot cells are protected), and then:
   - uses the **official plot outlines** wherever cells were read and lie on free society land (6,072 plots). Each outline is cleaned: a box on the block's axis, its own rectangle where the row is turned, or a polygon of at most five corners. Shapes with no neighbour of similar size are dropped as strays (124: pieces of lettering);
   - where the print does not resolve single plots, splits the street block into plots of the official size, but only on land that some block map actually draws on (4,942 plots, including 262 plot-sized gaps in rows and 99 wider unread pieces, which are cut along the streets the sheet shows);
   - **streets between the plots** (`corridor_lines` in `make_data.py`): the land left between the placed plots is thinned to its centre lines at 1 m; a line is kept where the corridor is 6 to 26 m wide and the block map shows street space there. Each is drawn as a 5 m carriageway in a 40 ft reserve, so a street has one width and runs straight between junctions (15.3 km in 178 pieces). Dead ends under 28 m and lone stubs are dropped;
   - leaves society land that every block map shows blank as open ground (layer `open` in `blocks.geojson`), with no plots.
   - Regeneration takes about 40 seconds.
5. **Houses (new):** building footprints inside the society are matched to plots. A plot with a footprint is `built`; the footprint becomes a house model at its real position. Footprints that lie on a mapped road (24) or inside a named site are left out.
6. **Development class (new):** share of built plots within 150 m of the plot: High from 30%, Medium from 8%, otherwise Low. This is a simple measured stand-in until the ML model exists.
7. **Main gate (new):** position measured on Esri World Imagery (31.50934 N, 73.06941 E, where the Main Entrance Road leaves Sargodha Road); the official Block A map draws the gate across that road. It is a point feature in `landmarks.geojson`, centred between the two carriageways.
8. **Measured sizes:** carriageway widths, roundabout sizes and the nalla were measured on Esri World Imagery at zoom 19 (0.25 m per pixel).

Reference values:

- Local metre frame: equirectangular, origin 73.0875 E, 31.525 N, latitude of reference 31.525.
- Roundabouts (lon, lat): A/B 73.082462, 31.520554; B/C 73.087766, 31.52568; Block A south-west 73.078424, 31.511277.
- Boulevard bearing about 48.6 degrees. 1 kanal = 505.857 m².

To regenerate and check (the first command is only needed when re-reading the sheets; it downloads them into `tools/source/cache/`, about 1 minute):

```powershell
python -I tools/trace_plots.py --debug debug_out
python -I tools/make_data.py --preview preview.png
python -I tools/audit.py
```

`tools/trace_sheets.py` (the named sites of Blocks B to F) still needs working files that are not in the repo; its result is saved in `plan_features.json`, so normal regeneration does not need it.

To refresh the building footprints: query Overture Maps `theme=buildings/type=building` for the bounding box 73.066, 31.501, 73.106, 31.542 (DuckDB with the httpfs and spatial extensions, bucket `s3://overturemaps-us-west-2/release/<release>/`), keep `sources[1].dataset`, and write the polygons to `tools/source/buildings_fda.geojson`.

## 8. Where each thing comes from

| Thing | Source | Trust |
| --- | --- | --- |
| Block positions, the 120 named sites | Official block maps, georeferenced | Good; none invented |
| Official area of 47 sites | Kanal figure printed on the maps | 37 within 25%, 10 too small |
| 6,072 plot outlines (`layout: Official block map`) | Official block maps, registered to the real streets | Good to a few metres; checked over satellite imagery |
| 4,942 plot outlines (`layout: Generated in the street block`) | Split of the street block at the official size | Not the real plots; the street block is real |
| Plot numbers | Running numbers per block | Not the official numbers |
| Official road widths (202, 110, 85, 60, 40 ft) | Official maps | Good |
| Paved widths, roundabout sizes, nalla, main gate position | Measured on satellite imagery | Good |
| Streets from OpenStreetMap | OpenStreetMap | Real streets |
| Streets between plot groups (15.3 km) | Centre lines of the corridors between the placed plots, where the block map shows street space | Follow the official layout to a few metres; rougher in Block F |
| 119 planned 40 ft street pieces | Inserted by the generator in generated street blocks | Not on any map |
| Houses, `built`, `dev_class` | Building footprints detected on satellite imagery (Google Open Buildings 2023, Microsoft) | Real positions; the footprint data is about 3 years old, so newer houses are missing |
| Storeys and house appearance | Assumed from footprint size | Not real |
| Plot status | Sample values, labelled as such | Not real |
| Society boundary | Built from the society parcels and sites | Approximate |

## 9. Audit results at this commit

Data audit (`tools/audit.py`, run on 14 November 2026 after the last regeneration):

| Check | Result |
| --- | --- |
| Plots | 11,014 (official outlines 6,072, generated 4,942) |
| Named sites | 120, plus the main gate |
| Boundary area | 6.81 km² |
| Plots overlapping a carriageway, right of way, the nalla, a site or another plot | 0 |
| Plots outside the boundary | 0 |
| Plots more than 6 m from any road reserve | 303 (2.8%), official outlines, about a third of them in Block F |
| Plots 3 to 6 m from a road reserve (registration gap) | 29 |
| Duplicate site names, overlapping sites | 0 |
| Empty land patches over 600 m² | 0 |
| Plots within 0.85 to 1.2 times their size class | 8,204 |
| Plots smaller than 0.85 times | 2,140 (81 below 0.6 times) |
| Plots larger than 1.2 times | 670 |
| Plots that are not near-rectangular | 113 |
| Plot outlines with four corners | 10,150 of 11,014 |
| Sites under 400 m² | 4: Masjid (Park F-2), Dispensary (D), Shops (Park D-5), Park C-5 |
| Main gate | Present; carriageway centre lines 8.5 m either side, span 30.2 m |
| Buildings | 355 footprints; 236 built plots; 111 houses stand on land that is not a plot in the model; 0 on a carriageway |

Plots per block (official outlines / generated): A 1,858 (1,151 / 707), B 1,629 (1,027 / 602), C 1,404 (775 / 629), D 2,149 (808 / 1,341), E 2,131 (1,596 / 535), F 1,843 (715 / 1,128).

Built plots per block: A 127, B 9, C 1, D 9, E 6, F 84. Development class: Low 9,974, Medium 1,024, High 16.

Sites more than 25% below their official area (official kanal, then modelled kanal): Commercial Zone 12.72 / 9.3; Commercial Centre (D) 6.5 / 3.3; Commercial Centre (E) 6.5 / 4.2; Park A-1 18.8 / 11.1; Park A-4 3.69 / 2.7; Park A-5 14.34 / 9.8; Park (4.51 kanal) 4.51 / 2.1; Park B-2 (north) 1.76 / 0.9; Park B-2 2.95 / 1.9; Park B-1 16.55 / 9.1.

Browser tests (headless Chrome, software rendering, 14 November 2026):

| Test | Result |
| --- | --- |
| Page loads, no errors from the map code | Yes, about 12 s (the old `bg.js` `drawImage` error is still there and is not the map's) |
| Model audit `?audit=1` | 117 sites checked, 0 offenders |
| Main gate | Renders across the entrance road; found by search, tour and `?lm=121` |
| Houses | Render on their plots; clicking a house selects its plot |
| Coordinates | Typing a plot's own latitude and longitude into search returns that plot (every 25th plot tested, 0 wrong) |
| The five flaw screenshots Taha sent (zig-zag road, missing plot in a row, bare tan land, hexagon plots, odd road branches, all in Block A) | Each spot re-rendered in 3D and checked by eye: clean |
| Satellite ground | Plots lie on the land between the real roads; 3D houses stand on the houses in the photo (checked by eye in Blocks A and E) |
| Day, evening, night | All three render |
| Real-world tab (CesiumJS) | Loaded with the earlier data on 13 November; not rerun after the last regeneration |

## 10. Known flaws and things not verified

Layout:

- **4,942 plots are still generated,** because the print of the block maps is too coarse or too busy there (watermark, plot numbers touching the lines). Block F's sheet is 2.1 m per pixel and Block D's southern half uses very small plots; these two blocks have the most generated plots. Each plot says which kind it is.
- **Plot numbers are running numbers,** not the official plot numbers. The official numbers are printed inside the cells and could be read with OCR; this has not been done.
- **About 710 plot cells were read but not placed,** because they fall on a mapped road reserve or outside society land. The commercial rows along the boulevard are the main case; they are filled with generated plots instead.
- **303 official plots (2.8%) have no street within 6 m.** A corridor is only drawn as a street when it is found between placed plots and confirmed by the sheet; where plots were not read the corridor is not found. Block F (coarse sheet, no confirmation possible) is the roughest: its new streets bend more and some stop at open ground.
- **Streets found between plots are centre lines of the gaps,** simplified to 3 m. They are straight and of one width, but a junction can sit a few metres off.
- **The whole map has not been checked spot by spot.** The five reported spots, one area in Block D and one in Block F were checked in 3D; the rest relies on the audit.
- **Registration is good to a few metres, not exact.** Block A's sheet (1.23 m per pixel, curved streets) fits least tidily.
- **Ten sites are too small** (list above).
- **Block boundaries are approximate.** The split points between neighbouring blocks were chosen, not read from a map.
- **No feature-by-feature overlay check of the named sites** has been done yet (section 11).

Houses:

- **The footprint data is from about 2023.** Houses built since then are missing. Google Earth could not be used directly (no programmatic access); Esri World Imagery and the open footprint datasets were used instead.
- **115 houses stand on land that is not a plot in the model** (open land, generated green space, or the edge of the society). They are drawn but belong to no plot.
- **House appearance and storeys are assumed.**

Data honesty:

- Plot status is a sample value. The panel now says "Sample value (no society record yet)" with confidence Low.
- The development class is a simple count of nearby houses, not the ML model.

Graphics:

- **Buildings are still assembled from simple shapes** with textures drawn in code. No ready-made glTF models, photo textures or ambient occlusion were added in this session.
- **Speed on real hardware is untested.** All testing used software rendering on Taha's PC.

Integration:

- **`plot.html` and the top search bar use an old 60-plot sample** in `assets/app.js`, so they do not match the map plots. These are Mursaleen's pages.
- **The Cesium tab is untested with a token** (terrain and World Imagery), and it does not draw the houses or the gate.
- **The report and README still say React and scikit-learn** and do not mention three.js.

## 11. Suggested order for the next work

1. Scan the whole map block by block in 3D for remaining layout flaws (Block F first), and fix them at the source.
1. Raise the share of official plot outlines: fetch higher-resolution block maps if they exist, or tune `trace_plots.py` per sheet (Blocks D and F first).
2. Read the official plot numbers with OCR and replace the running numbers.
3. Fix the boulevard corridor so the commercial rows read from the sheets can be placed.
4. Overlay each block sheet on a top-down render and list every named site that is misplaced, missing or the wrong type. `trace_plots.py --debug` writes an overlay image per sheet.
5. Check each of the ten undersized sites.
6. Rerun `tools/audit.py` and the `?audit=1` model audit after any change.
7. Test the page on the laptop that will be used for the viva.

## 12. Graphics

Done in this session: the main gate model, houses with porches, roof stair rooms, tanks, boundary walls and gates, evening light with long shadows, bare scrub ground for unplotted land.

Still open, in the order discussed with Taha:

1. Replace the box buildings with ready-made glTF models (mosque, school, hospital, shops, trees).
2. Use photo-based textures for asphalt, grass, paving, brick and soil.
3. Add ambient occlusion.
4. Softer shadows and distance haze.
5. Plot detail: corner markers, plot number on the ground when zoomed in.
6. Better water for the nalla and park lakes.
7. People, running fountains.
8. A cinematic opening camera move and icon labels.
9. Level of detail, so the extra graphics stay fast.

Models must stay labelled illustrative. Plots must stay land parcels.

## 13. Open items waiting on Taha

- Cesium ion token.
- Real plot records from the society, if he can get them.
- Whether to open the pull request for Mursaleen.
