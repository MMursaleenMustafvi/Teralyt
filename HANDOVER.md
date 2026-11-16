# Terralyt 3D map: handover

Updated 15 November 2026 (afternoon), on branch `feature/3d-map`. The commit that contains this file is the current state: **plots, plot numbers and Block X from the emap.pk plan** (section 7), with **service roads measured from Google Maps and satellite, two lanes per main carriageway, and full screen** (section 9a). Earlier states: `7aa34ae` (plots from the six fdacity.pk block maps, before emap.pk), `d2884cf` (before the plots were read from the block maps), `206b1f4` (first version with official plots, the gate and houses; it had zig-zag streets and odd plot shapes, fixed since).

This file is for whoever continues the 3D map work in a new chat, with no access to the earlier conversation. It says what exists, how it was built, what has been checked, and what is still wrong or unverified. Read it together with `CLAUDE.md` in the same folder, which holds the project rules and the code reference. Where the two disagree, trust this file for the current state and `CLAUDE.md` for the rules.

## 1. The project in short

Terralyt is a Final Year Project at FAST-NUCES (Chiniot-Faisalabad), 2026. It shows a Pakistani housing society as an interactive 3D map, rates its development Low / Medium / High, and gives a 5-year forecast. The pilot society is **FDA City, Faisalabad** (about 31.522 N, 73.086 E).

- **Taha Saleem Sheikh** owns the 3D map and the AI/ML model. This handover covers only the 3D map.
- **Muhammad Mursaleen Mustafvi** owns the web UI and the GitHub repo.
- **Rahmeen Nasr** is the third team member. Supervisor: Ms. Mahzaib Younas.

## 2. What Taha wants (read this before changing anything)

These rules came from repeated corrections. Earlier work was rejected each time one of them was broken.

1. **Satellite imagery is only for measuring real things:** the nalla (storm drain), roads, roundabouts, their widths, the society boundary, and (since 13 November 2026, at his request) which plots have a house on them.
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
| Latest code commit | The commit containing this file: plots from the emap.pk plan (`tools/emap_plan.py`) |
| Pull request | Not opened yet |
| `main` | Untouched by this work |
| Cesium ion token | Not provided; the real-world tab has only been run with OpenStreetMap tiles and flat ground |

## 5. How to run

Since 16 November 2026 the site is a React app (Vite). Node.js is needed: on Taha's PC a portable Node 24 LTS is in `C:\Users\Taha\tools\node` (add it to PATH, or install Node 20+ from nodejs.org).

```powershell
cd C:\Users\Taha\Teralyt
$env:Path = "C:\Users\Taha\tools\node;" + $env:Path    # only on Taha's PC with the portable Node
npm install        # once
npm run dev        # then open http://localhost:5173/
```

Pages (hash routes): `#/` home, `#/map`, `#/search?q=B-12`, `#/plot/2500`, `#/trends`, `#/login`, `#/dashboard`, `#/society`, `#/admin`. Map options: `#/map?plot=B-12`, `?id=2500`, `?lm=121` (main gate), `?block=C`, `?layer=cls`, `?time=evening|night`, `?ground=satellite`, `?view=earth`, `?quality=high`, `?audit=1`. Demo accounts: `user@terralyt.pk`, `head@terralyt.pk`, `admin@terralyt.pk`, password `Terralyt@2026`.

Production / testing: `npm run build`, then `cd dist; python -m http.server 8080` and open `http://127.0.0.1:8080/`. The Playwright test scripts use that port.

Machine quirks:

- `git` is at `C:\Program Files\Git\cmd` and may not be on PATH in a tool shell.
- **Use Python 3.12** (`C:\Users\Taha\AppData\Local\Programs\Python\Python312\python.exe`, the first `python` on PATH). Since 15 November 2026 Windows Application Control blocks shapely's DLL in Python 3.15 ("An Application Control policy has blocked this file"). Python 3.12 has shapely, numpy, pillow, matplotlib, scipy, scikit-image, opencv and playwright. Run the tools with `python -I`.
- `tools/shoot.py` takes headless screenshots with the installed Chrome and software rendering. Run one capture at a time. The page now loads in about 12 seconds.
- **Only one server may run on port 8000.** Windows lets several `python -m http.server 8000` processes share the port; the browser then reaches a dead one and shows `ERR_EMPTY_RESPONSE` ("localhost didn't send any data"). This happened on 13 November. Before starting a server, stop the old ones:

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'http\.server' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

How to check one spot after a change: regenerate, rebuild, serve `dist/`, then load the page and fly to the spot, for example `python -I tools/shoot.py "http://127.0.0.1:8080/#/map?plot=A-1059" out.png --el "#stage"`, and look at the image. Taha reports flaws as close-up screenshots; the plot numbers in them locate the place, but **plot numbers shift after every regeneration**, so note the plot's latitude and longitude (shown in the side panel, or `lat` / `lon` in `plots.geojson`) before regenerating and search by `lat, lon` afterwards.

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

## 7. How the data was made (since the evening of 14 November 2026)

**The plot layout now comes from the whole FDA City plan published on emap.pk**, not from the six fdacity.pk block maps. emap.pk (https://emap.pk/fda-city-faisalabad-map) shows a redraw of the FDA plan as map tiles over Google satellite at zoom 19 (about 0.25 m per pixel), with every plot outline and plot number printed sharply. It is a **newer revision** than the fdacity.pk maps: it has **Block X** in the north-east (where fdacity.pk shows "Multi-Purpose Uses" and a proposed university, stadium and IMAX theatre) and a 216-kanal graveyard at the north-east end of the boulevard. Taha compared both on 14 November and asked for every plot to be taken from it. It is a third-party redraw, not an FDA file; every plot says so in `layout`.

emap.pk's own placement on the satellite photo is off by about 4 m (up to 13 m in Block D), so its positions are not used as they are.

1. **`tools/emap_plan.py`** (stages `fetch, cells, split, roads, register, ocr, rapid, digits, write`; each caches in `tools/source/cache/emap/`, git-ignored; a full run takes about 30 minutes):
   - `fetch`: downloads the 4,050 zoom-19 tiles.
   - `cells`: every closed plot outline. Plot lines are told from the printed numbers and the watermark by being thin, straight and long (oriented line filters over 6 m); digits are thick short strokes (white digits on the red commercial plots are found separately). About 14,100 outlines.
   - `split`: outlines that hold two or more printed numbers with no line between them (the plan sometimes omits a divider) are cut halfway between the numbers.
   - `roads`: the plan's street space and plot colours, at 0.5 m.
   - `register`: the plan's street space is matched to the OpenStreetMap streets in 1,523 overlapping 260 m windows; 391 outliers dropped; a smooth displacement field is fitted. Shift before: 3.7 m median, 8.2 m at the 95th percentile. Residual after: **0.65 m median, 1.7 m p95** (per block 0.51 to 0.72 m).
   - `ocr`: the number in each cell, turned upright, read by Tesseract (`winget install UB-Mannheim.TesseractOCR`) in four turns.
   - `rapid`: RapidOCR (PaddleOCR recogniser on ONNX) reads every crop too, via `tools/rapid_ocr.py` in Python 3.12 (`py -3.12 -m pip install rapidocr_onnxruntime`; set `TERRALYT_RAPID_PY` for another interpreter). About 55 minutes.
   - `digits`: the three readings (Tesseract, RapidOCR, the digit recogniser) are combined by vote; where they disagree, the one its row agrees with wins. A digit recogniser trained on Tesseract's sure readings re-reads the rest (touching digits are cut apart); a 4 or 7 much narrower than the other digits is a 1; numbers made of 0 1 6 8 9 are turned the same way up as their neighbours; neighbours in a row then correct each other (numbered one after the other).
   - `write`: `tools/source/emap_layout.json` (registered cells with numbers), `emap_road.png`, `emap_plotcol.png`.
2. **`tools/make_data.py`** uses `emap_layout.json` when it exists (`--sheets` goes back to the fdacity.pk block maps):
   - society land is what the plan draws (Motorway City stays a hole);
   - every plan cell becomes a plot; where the road as built is a few metres wider than drawn, the plot is trimmed to the road edge instead of dropped;
   - **streets**: OpenStreetMap where mapped; elsewhere the plan's own street space, thinned to centre lines (38 km). The "planned 40 ft streets" the generator used to invent are gone (0 now);
   - Block X sites are read from the plan's colours (schools blue, masjids yellow, grid station grey, parks green, graveyard brown, the two government housing sites orange and pink, drawn as reserved land with a name board);
   - plot numbers: misreads past a block's numbering range are corrected from neighbours (141) or left out (23). The plan numbers plots per sub-block, so numbers repeat inside a block: plot IDs are `D-108`, and where the number repeats, `D-108 (D2)` with the **estimated** sub-block (numbering areas rebuilt from the number sequences, named after the nearest "Park D-2"), plus a letter if it still repeats. `plot_number`, `sub_block`, `number_source` are in each plot;
   - regeneration takes about 5.5 minutes.
3. Houses, development class, the main gate, road widths and the nalla are made as before: building footprints from Overture Maps (Google Open Buildings 2023, Microsoft), gate and widths measured on Esri World Imagery.

To redo everything:

```powershell
python -I tools/emap_plan.py            # only when re-reading the plan (about 30 minutes, needs Tesseract)
python -I tools/make_data.py --preview preview.png
python -I tools/align_roads.py          # only when re-measuring where the main roads run (then make_data again)
python -I tools/service_roads.py        # only when re-measuring the service roads (then make_data again)
python -I tools/audit.py
```

Reference values: local metre frame equirectangular, origin 73.0875 E, 31.525 N. Roundabouts (lon, lat): A/B 73.082462, 31.520554; B/C 73.087766, 31.52568; Block A south-west 73.078424, 31.511277. 1 kanal = 505.857 m².

## 8. Where each thing comes from

| Thing | Source | Trust |
| --- | --- | --- |
| 12,995 plot outlines (`layout: FDA City plan (emap.pk), registered to the streets`) | emap.pk redraw of the FDA plan, registered to the OpenStreetMap streets | Good: fit residual 0.65 m median; checked over Google imagery in every block |
| 62 plots (`Gap in a row of the plan`) | Plot-sized gaps in a plan row whose outline could not be read | Real gaps of the plan; outline approximate |
| 2 plots (`Generated in the street block`) | Small leftovers split at the plan's size | Not real plots |
| Plot numbers (`plot_number`) | Printed on the plan, read by OCR (Tesseract, RapidOCR and a digit recogniser, combined by vote and checked against the neighbours) | 12,707 plots (97.3%) numbered; about 98.5% right in a 144-plot spot check; 542 not confirmed by a neighbour (said in `number_source`) |
| Sub-block (`sub_block`) | Estimated from the numbering and the nearest park name | Estimate, labelled so |
| Block X layout and sites | emap.pk plan (newer revision) | Not on the fdacity.pk maps; Zameen says the land is still being acquired |
| Named sites of Blocks A to F | fdacity.pk block maps (unchanged) | Good |
| Streets in OpenStreetMap | OpenStreetMap | Real |
| Other streets (38 km) | The plan's street space | Follow the plan to under 1 m |
| Houses, built / vacant, development class | Building footprints (about 2023) | Real positions, about 3 years old |
| Storeys, look of houses, plot status | Assumed / sample | Not real |

## 9. Audit results at this commit (14 November 2026, evening)

`tools/audit.py`:

| Check | Result |
| --- | --- |
| Plots | **13,059** (A 2,244, B 1,577, C 1,718, D 2,165, E 2,203, F 1,521, X 1,631) |
| Plots overlapping a carriageway, right of way, the nalla, a site or another plot | 0 |
| Plots outside the boundary | 0 |
| Plots more than 6 m from any street | **26 (0.2%)** (was 303) |
| Streets invented by the generator | 0 (was 130) |
| Plan plot cells that became no plot | about 250 of 13,559: OpenStreetMap draws a road over the plan's first row (mostly the boulevard service roads) |
| Empty land over 600 m² | 2 patches: 2.2 ha east of Block E (outside the plan, inside the outline) and 0.2 ha by the motorway |
| Sites | 132 plus the main gate; 13 of them in Block X |
| Plot numbers | **12,707 numbered (97.3%)**; 542 not confirmed by a neighbour; 352 without a number. Spot check of 144 random plots against the plan: 142 right (about 98.5%) |
| Buildings | 492 footprints; 359 built plots; 0 on a carriageway |

Browser test (headless Chrome, software rendering): page loads; 13,059 plots and 134 landmarks; model audit `?audit=1`: 0 parts outside their sites; Block X renders; search `12 F4`, `D-108`, `X-1450` finds the right plots; the side panel shows plot number, estimated sub-block, area in marla and the source. The old `bg.js` `drawImage` error is still there (not the map's).

Google check: each block's plots were drawn over Google satellite (zoom 19): plots lie between the real roads and built plots hold their house. Google and Esri imagery agree to about 1.2 m here.

### Fixes of 15 November 2026 (Taha's screenshots: jagged plots, stray road stubs, roads off the asphalt, 6-lane boulevard)

- **Jagged plot edges**: the printed number and the red emap.pk watermark bite notches out of plan outlines. Each outline is now filled out to its own hull wherever no neighbouring plot is there (`EmapPlan.cells`). Notched plots: 277 -> 36.
- **Stray road stubs** in medians and verges: plan streets that run inside a main road's corridor, or are short pieces that do not join two roads, are dropped; streets end square, not rounded. Two OSM streets side by side (one on the plan's street, one 5 m off) no longer happen: OSM residential streets are moved onto the plan's street space (`align_to_plan`, 336 streets, median 1 m).
- **Main roads on the real asphalt**: `tools/align_roads.py` measures each main OSM way's sideways offset on Google satellite (zoom 19) and writes `tools/source/road_offsets.json`; `make_data.py` applies it (37 ways, median 1.5 m, max 4.8 m). Esri's photo here is too hazy for this.
- **Boulevard lanes**: (superseded on the afternoon of 15 November, see 9a: the carriageways do carry a dashed lane line, two lanes per side.)
- **Park C-3** is placed on the triangle the newer plan names "Park C-3" (the old sheet put it on a sliver); "Park (Block C west)" was the same triangle and is gone.
- Building footprints: the Overture release of 21 October 2026 has nothing newer inside FDA City than our data (Google 2023-05 and Microsoft), so houses built after mid-2023 are still missing.

## 9a. Main road, service roads and full screen (15 November 2026, afternoon)

Taha sent four pictures: the 3D view along the Main Entrance Road by Block A / Block F, a street with a sideways jog, Google Earth of the footbridge by the gate (two lanes each way with a dashed line), and Google Maps by the gate ("Service Road" on both sides, slip roads into the main road). He asked for: the main road as 4 lanes (2 each way), service roads where Google Maps has them and not elsewhere, proper road markings, a full audit with every inconsistency fixed, and full screen.

What was wrong, and what was done:

| Finding | Fix |
| --- | --- |
| Main carriageways painted with edge lines only. Google satellite (zoom 19/20, e.g. at the footbridge 70 m from Sargodha Road) shows a dashed line in the middle of each carriageway: two lanes each way. | `society3d.js`: dashed lane line (3 m dash, 6 m gap) plus solid edge lines on every `main` carriageway; traffic in two lanes each way. |
| Service roads missing: none along the Main Entrance Road (Google: both sides, full length, slip roads at the gate), none on the south-east side from the south-west roundabout to roundabout A/B, none on the north-west side for the last 107 m before A/B, none on the south-east side for 620 m north-east of roundabout B/C. OpenStreetMap does not map them (checked against a fresh Overpass download: no new ways). | New `tools/service_roads.py`: walks every main carriageway every 4 m; Google's road map without labels decides where a service road exists; the asphalt band on Google satellite gives its centre line and width. 6 lines, 3.6 km, written to `tools/source/service_roads.geojson`; `make_data.py` adds them (class `service`, `source: Measured ...`). Checked on straightened corridor images: every line lies on the real service-road asphalt. Beyond 600 m north-east of B/C there is no service road (undeveloped Block X land), and none is drawn. |
| Plan plots on the real service roads: along the entrance road the plan draws the "202 ft" road only 27 to 33 m between its commercial rows, while the built road with service roads is about 57 m, so rows A-1.. and A-161.. lay on the service roads. | Plots are trimmed back to the real road edge (they keep their plan numbers); a trimmed plot is kept when at least 35% of it remains (was 50%), so the commercial rows stay as numbered plan plots instead of being replaced by generated ones (0 generated plots now). |
| An OpenStreetMap street tagged residential (way 860021161) runs along the real south-east service road north-east of B/C: two roads side by side. | Streets running along a measured service road are cut back there (5 streets) and joined onto the service road. |
| Outside the society outline (by the gate) the service road was drawn fused with the main carriageway, and lamps stood on it. | Paved strips with painted kerbs between main road and service road are laid out there too (on site about 1 m by the gate); no lamp is placed on a service road; the service lines are kept in `roads.geojson` out to the gate. |
| Service roads painted with a dashed centre line; on site they have none. | Removed. |
| Cars on two-way roads drove on the right. Pakistan drives on the left. | Fixed in `buildCars`. |
| Sideways jogs in plan streets (the street in Taha's picture, 31.50906, 73.07691, and 9 more): the plan draws the nalla with a kink there while the real nalla is straight, and big "ROAD 40'-0" WIDE" lettering or the watermark breaks the plan's street space. | `plan_street_lines`: small holes in the street space (under 150 m², not plots) are filled; new `dejog()` takes S-shaped steps (parallel legs, up to 8 m sideways within 20 m) out of every traced plan street, keeping its ends. Plan-street jogs: 10 to 0. |
| Short dead-end pieces of traced street lying alongside a real street (13 stubs under 15 m). | Pieces under 20 m that run parallel to a street within 10 m are dropped (10). 6 stubs remain: 4 are real OpenStreetMap pieces (a motorway link, a median U-turn gap). |
| Plots with no street in front (40 more than 6 m from any street): site outlines from the older fdacity.pk maps (Park A-2, a Block D park and 17 others) spill over the newer plan's street, so that street was never traced. | Only a site's interior (8 m in from its edge) stops a plan street; a site the traced street runs over is cut back to the 40 ft reserve (19 sites, their 3D frames and areas updated, holes for plots kept). 40 to 26 plots. |
| Plot-number labels drew over the details panel. | The label layer has its own stacking context (`z-index:1`). |
| No full screen. | Button under the compass and the F key; the map stage fills the screen with the search box and the selected plot's details over it; Esc leaves. Works for both tabs; falls back to filling the window where the Fullscreen API is missing (iPhone Safari). |

New audit checks (`tools/audit.py`): S-shaped steps in street lines, dead-end stubs under 15 m, service-road summary. `python -I tools/audit.py . all` lists every stub.

Audit at this commit: 13,127 plots (13,078 plan outlines, 49 gaps in a plan row, 0 generated); 0 plots on a carriageway, right of way, the nalla, a site, another plot or outside the boundary; plan-street jogs 0 (7 small steps of 1.6 to 2.3 m remain in OpenStreetMap streets at junctions); stubs 6; plots more than 6 m from any street 26 (was 40); service roads 12 lines, 7.0 km (6 measured); non-rectangular plots 273 and plots under 0.6 of their official size 179 (both up by about 10 and 16: the trimmed entrance-road commercial plots); 7 facilities more than 25% off their official area (unchanged).

Tools for checking a spot: `tools/overlay.py` (data over Google satellite, the Google road map or the emap.pk plan).

## 9b. Houses, street furniture, gate and turning the view (15 November 2026, evening)

Taha's next screenshots: house A-270 standing half on vacant A-271; houses over A-4 (A2)/b and A-14/d; trees planted on plot A-102 inside the PMU Office wall; at night a guard booth, a barrier, a lamp and a palm standing on the road by the main gate; a lamp and a tree on the asphalt at a median opening; a kerbed strip ending abruptly. He also said turning the view did not work (full screen did), and asked for emap.pk to be used.

| Finding | Fix |
| --- | --- |
| 268 of 491 house models lay partly on a vacant neighbouring plot. Building footprints (satellite, 2023) do not follow the plan's plot lines: some owners built over two plots, other footprints are 1 to 3 m off. The house was drawn as the footprint's bounding rectangle, which is larger again. | `make_data.py`: where a footprint covers at least 30 m2 and a fifth of a neighbouring plot, the house was built over both: it is split at the plot line and both plots are built (106 footprints). Where it only pokes over, it is trimmed to its own plot (244). Each house is drawn in the largest rectangle that fits inside its piece, aligned with the plot (`inscribed_rect`). Houses on no plot are kept off the plots they touch. Result: 572 houses on 462 built plots (was 491 on 359); audit: 0 houses outside their own plot, 0 on another plot. |
| Sites with plots inside them (11: Markazi Park, Hospital A, Fire Brigade, PMU Office, Park A-2, Park B-1 and others; the plan cuts those plots out as holes) were modelled from their outer edge only: trees, ground and buildings over the plots. | The 3D kit (`makeKit(..., holes)`) knows the holes: ground has the holes, the wall runs round them, trees and parked cars stay off them, the model's rectangle (`inscribedRect`) avoids them; `?audit=1` reports any part standing on a plot inside a site (`on_plots_inside`). |
| Gate: the towers, guard rooms, lamps and canopy columns stood on the service roads added on 15 November (the model was sized to the main carriageways only), and the barrier arm lay across a lane. | `make_data.py` writes the asphalt bands across the gate (`asphalt` on the gate feature, measured from the carriageways); `buildGate` puts the towers 0.8 m beyond the outermost asphalt, the pier, the guard room and the barrier posts (arms raised) on the 7.5 m median, the beam over every lane; no canopies. |
| Trees, palms and lamps on asphalt at median openings, junctions and bends. | `society3d.js`: every tree and lamp is tested against the carriageway polygons (`asphaltIndex`) and dropped if it stands on a road (`api.furnitureOffRoad` counts them). |
| Measured service road and the OpenStreetMap one ran side by side for a few metres with a kink (31.5142, 73.0805). | A measured service road that runs on into an OpenStreetMap one joins it (end snapped, overlap dropped, then `dejog`). |
| A drag that began on a site name or a block letter did nothing (those labels caught the mouse): likely why "turning does not work". | `passToMap` in `society3d.js`: a press on a label is passed on to the map, so dragging pans or turns; a press that does not move is still the label's click. |
| Five sites from the older fdacity.pk maps lie where the newer plan has plots or a street (Mosque F-1 on plots 281-295, Shops Block A on a street, Park C-3 on plots 87-112, Dispensary C and Shops Park C-1 as slivers); only slivers were left and a mosque model stood on two plots. | `make_data.py` drops a site with under 30 m2 of usable land (2.5 m in from every edge). The plan's real dispensary in Block C (the green "DIS" site) is not placed yet. |
| Turning and tilting needed the right mouse button (impossible on a touchpad). | Buttons under the compass: turn left / right, tilt up / down (click, or hold to keep turning); drag the compass sideways; arrow keys; Shift + drag (built into the controls). All work in full screen. `api.turn(deg, tilt)`. |

### Later on 15 November (Taha's screenshots of bridges, the service road, a broken street, a "park")

| Finding | Fix |
| --- | --- |
| No divider between a main carriageway and its service road by the gate and along the Main Entrance Road: the asphalt of both is 1 to 2 m apart there, so the road faces left no strip and the two roads ran together. | `make_data.py` lays out a kerbed divider (at least 0.9 m) from the two centre lines wherever they run side by side less than 3 m apart, open where a side street or slip road joins (9 pieces, 1.1 km). |
| Cars on the service roads drove both ways (one looked wrong-way). | A service road is one-way in the direction of the main carriageway beside it (line oriented in `make_data.py`, `oneway: true`). |
| Bridge railings running across the road (F-256, F-319) and a broken junction where Iqra Road (a dual road, two one-way carriageways 10 m apart, confirmed on Google Maps) crosses the nalla. | Crossings close together are one bridge: the carriageways of a dual road share one bridge with railings on its outer edges (4); a side street meeting a road at the channel gets no bridge of its own (3). 37 crossings, 30 bridges. |
| A 40 ft street broken by a green patch (F-33 / F-132) and 5 more streets broken into pieces (printed numbers or names across the plan's street). | `join_street_gaps`: two street ends facing each other in line under 16 m apart, with no plot between, are joined (then straightened). |
| A plan street tapering to a point behind A-177 (A1) where plots press on it. | Plan-street asphalt narrower than 3 m is cut off (morphological opening of the new carriageway). |
| A "park" by F-106 that the plan labels EXISTING GRAVE YARD (brown). | Open land the plan paints graveyard brown (63% here) becomes a graveyard site (`EmapPlan.colour_share`, `GRAVE_COLOURS`): 2 found. |
| The browser could keep an old copy of the map scripts after an update. | Version tags on the module imports (`society3d.js?v=...`, `models3d.js?v=...`, `map3d.js?v=...`); change them with each update. |

The road fork with a long green island near A-212 / A-233 is drawn on the plan that way (two lanes round a planted island) and is kept.

emap.pk: the plots, plot numbers, streets inside the society and Block X already come from it (section 7). It does not cover the area outside the society (the gate and the first 300 m of the Main Entrance Road), so there the road layout is OpenStreetMap plus measurements on Google imagery.

## 10. Known flaws and things not verified

- **Entrance-road commercial plots are trimmed**: the plan's rows along the Main Entrance Road (A-1 to about A-31, A-161 to A-194) are shallower than drawn because the real road with its service roads is wider than the plan draws it. Only the FDA's original plan can say where these plots really are.
- **26 plots still have no street within 6 m** (A-244 to A-248 by Park A-2, 4 in Block B, 2 in C, 3 in D, 2 in E, 6 in F, 3 in X; `python -I tools/audit.py . all` lists them with positions). Tried on 16 November: a second tracing pass without the main-road corridor limit and with the outline widened by 9 m fixed only 1 plot, added 2 dead-end stubs and doubled the run time, so it was removed. The plan does draw the street beside Park A-2 (grey band between plots 242 to 251 and the park), but the tracer never sees it as street space; the next step is to look at `emap.road` there (`tools/overlay.py 31.51208 73.0714 --base plan`) and at what blocks it.
- **Lane positions**: lane lines are painted at the centre of each OpenStreetMap carriageway line; where that line is 1 to 2 m off the real asphalt (for example way 376583796 between the south-west roundabout and A/B), so are the lane lines.

- **emap.pk is a third-party redraw** with its watermark. Ask FDA for the original plan (CAD or PDF) and rerun with it.
- **Plot numbers are OCR**: 2.7% of plots have none and about 1.5% of the numbers are wrong (very small print, upside-down numbers made of 1, 6, 8, 9). Each plot says in `number_source` whether a neighbour confirms its number.
- **Sub-blocks are estimated**, not read.
- **About 70 plan plot cells are not placed** (was about 250): they lie mostly on a road as built (176 more are trimmed to the road edge instead). The rule since 15 November: a plan plot is kept, trimmed, while at least 35% of it remains. Each left-out cell is listed with its reason when `TERRALYT_DEBUG` is set.
- Block X site purposes come from the plan's labels only.
- The Cesium tab now draws the houses and the main gate; it is still untested with a token (terrain, World Imagery).
- `plot.html` and the top search bar still use the 60-plot sample in `assets/app.js` (Mursaleen's pages).
- Houses are illustrative (real footprint and position, assumed look and storeys); speed on real hardware untested; the footprint data is from about 2023.

## 11. Suggested order for the next work

1. Taha: look at the main road (gate to the north-east end), Block X and a few plots per block, in full screen; send screenshots of anything wrong.
2. Give the 26 plots without a street their street (Park A-2 row: trim Park A-2's old outline to the plan; streets along the society edge: trace them with the outline buffered outwards).
3. Re-centre the main carriageway lines on the asphalt where they are 1 to 2 m off (rerun `tools/align_roads.py` with a two-lane model), so the lane lines sit on the painted ones.
4. Improve number reading for Blocks A and X (a better OCR model) and read the sub-block names printed on the plan.
5. Replace emap.pk with the FDA's own plan if it can be obtained.
6. Open the pull request for Mursaleen.

## 12. Graphics

Done on 13 November 2026: the main gate model, houses with porches, roof stair rooms, tanks, boundary walls and gates, evening light with long shadows, bare scrub ground for unplotted land.

Done on 15 November 2026 (night), Taha's "proper 3D models, photo textures, softer shadows":

| Item | What changed | Where |
| --- | --- | --- |
| Photo textures | Roads, grass, lawns, verges, vacant land, plots, footpaths, roofs, walls and gates use real photographs (CC0, ambientCG, 512 px, 0.5 MB in all; `assets/tex/`, credits in `assets/tex/README.md`, rebuilt by `tools/make_textures.py`). Each photo is tinted to the colour the map used before, so the palette and legend are unchanged. A shader blends each ground photo with a rotated copy of itself in patches and adds slow brightness changes, so the repeat does not show over a road or lawn. Facades are drawn on photographed plaster or brick. If the photos cannot load, the drawn textures stay. | `usePhoto`, `antiTile`, `photoWall` in `models3d.js` |
| Softer shadows | Sun shadows use a wider filter (PCF, radius 2.4) and let 14% of the light through (sky light), so edges are soft and shade is not black. | `society3d.js` (renderer and sun set-up) |
| Ambient occlusion (cheap) | Walls darken towards the ground (shader, by height); every building has a soft contact shadow on the ground round it; every tree a soft round shadow under it. No extra render pass, so it costs little. | `groundShade`, `aoSkirt` in `models3d.js`; tree shadows in `buildInstances` |
| Houses | Rebuilt as houses in Faisalabad's societies are built: stone plinth, plastered walls with sunshades over the windows and dark aluminium frames, floor slabs showing on the walls, a stone, brick or dark-tile feature panel on the front, a car porch with a terrace and steel railing (deep houses of 2+ storeys), a canopy over the door, parapet with coping, stair room with door, black and white water tanks, air conditioners, and on half the roofs a row of solar panels facing south. Each house is turned so that its front faces its street (490 of 572; the rest keep the long side), and each built plot's gate is on the side that faces the street. Steel gates have ribs. | `buildHouse` in `models3d.js`; `buildHouses` in `society3d.js` |
| Cars | A sedan body from its side profile with rounded edges, windscreens and side glass, wheels with rims, lamps (was two boxes). | `carGeometry` in `society3d.js` |
| Trees | Irregular crowns instead of perfect balls; soft shadow under each. | `shaded` in `society3d.js` |
| Weak devices | On phones and PCs with 4 cores or fewer the repeat-hiding shader and the tree shadows are off. | `createMaterials({ lite })` |

Cost, measured in headless Chrome with software rendering (same view): 4.30 million triangles before, 4.70 million after (+9%); a frame took 5.6 s before and 6.7 to 7.4 s after (software rendering only; on a graphics card these shaders are cheap). Model audit (`?audit=1`): 124 sites, no part outside its site. No page errors by day, evening or night.

Done on 16 November 2026 (the four open items above):

| Item | What changed | Where |
| --- | --- | --- |
| Trees with real leaves | Close to the camera every tree is built from leaf cards textured with photographed leaves (CC0, Poly Haven): compound leaves for the round crowns (neem, sheesham), long single leaves for the columnar Ashoka, fronds for the date palms on the boulevard, bark on trunks and branches. The cards are alpha-tested with alpha-to-coverage (smooth edges) and lit as a ball, so the crown looks round from every side; lower and inner leaves are darker. One 290 KB texture (`assets/tex/foliage.webp`, built by `tools/make_foliage.py`). | `treeNear`, `crown`, `frond` in `society3d.js`; `M.foliage` in `models3d.js` |
| Level of detail | Trees are instanced per 600 m patch in two versions: leaf cards near the camera, one low-poly crown far away (`treeFar`). Houses keep walls, roof and parapet everywhere; their small parts (porch, railing, stair room, tanks, solar panels, slabs, front panel) are merged per 500 m patch and drawn only near the camera. Each patch switches by its distance from the camera (`lodItems`, `updateLod`; 720 m for trees, 640 m for house details, with a little hysteresis). The overview now draws 2.79 million triangles instead of 4.70 million and a frame took 3.2 to 3.3 s instead of 6.7 to 7.4 s in the software-rendered test. If the leaf texture cannot load, the far version is used everywhere. | `society3d.js` |
| Ambient occlusion | Real screen-space ambient occlusion (N8AO 1.10.1, which handles the map's logarithmic depth buffer): soft shade in corners, under parapets, round tanks and where walls meet the ground. Half resolution, SMAA for the edges. **Graphics** button (and `?quality=`): Auto (default: on when this device draws a frame in under 20 ms without it, measured for 2.5 s after loading; off again if frames then take over 34 ms), High (on, details drawn 1.4 times further out), Fast (off, details only close by). Weak devices never switch it on by themselves. Loaded from jsDelivr only when switched on. | `setAO`, `autoQuality`, `setQuality` in `society3d.js`; import map and button in `map.html` |
| Light from the sky and distance haze | The environment map (ambient light and reflections) is rendered from the sky itself: the physical sky without its sun disc by day and in the evening, the night gradient at night, and the ground below the horizon; rendered again when the time of day changes. Glass and cars reflect the real sky colour. Exponential haze in the horizon colour fades distant land (about 9% at 3 km, 63% at 10 km by day; a little denser and warmer in the evening). The sky light is kept at 0.55 with a warm fill light, because the sky is blue and more of it made everything look cold. | `setSkyLight` in `society3d.js` |
| Large buildings | A stone plinth, the floor slabs showing on the walls and air-conditioner condensers on large roofs, added to every landmark building (schools, hospital, offices, mosque halls), as on the houses. | `k.building` in `models3d.js` |

Why the large buildings are not ready-made glTF files: no free model of these particular buildings exists (FDA City's own mosque, schools, hospital, offices), and a generic downloaded building would show a buyer something that is not there. Free models that do exist are either cartoon-style or photo-scanned with hundreds of thousands to millions of triangles each (Poly Haven's trees: 0.3 to 17 million). The procedural models are fitted to each real site, built from the official block maps, merged into few draw calls and now use the same photo textures as the houses. Real models of these buildings could come from the FDA's architectural drawings or from photos taken on site (photogrammetry); they would then be fitted to the site rectangle the same way (`inscribedRect`).

Still open:

1. Real 3D models of the large buildings from the FDA's drawings or site photos (see above).
2. Plot detail: corner markers, plot number on the ground when zoomed in.
3. Better water for the nalla and park lakes.
4. People, running fountains.
5. A cinematic opening camera move and icon labels.
6. Level of detail for the landmark buildings and the plots mesh, and a test on a real phone and an integrated-graphics laptop.

Models must stay labelled illustrative. Plots must stay land parcels.

## 13. React front end and the last map items (16 November 2026)

Taha decided the whole front end is React (as the project report says) and that the AI/ML development model counts as backend work, not now. Done:

| Area | What changed |
| --- | --- |
| Stack | Vite 8, React 19, React Router 7 (hash routes, so the built site works from any folder or static host), no TypeScript. three.js r169, three-mesh-bvh, N8AO and postprocessing from npm instead of the CDN import map. The old `*.html` pages, `assets/app.js` and `assets/iso.js` are removed (git history keeps them); `assets/` moved to `src/` (code, styles) and `public/` (logos, textures, `bg.js`). |
| Real data everywhere | The 60 sample plots are gone. `tools/make_index.py` (run by `make_data.py`) writes `data/plots_index.json` (every plot, 1.1 MB, repeated text stored once) and `data/outlines/<block>.json`; the search, plot, dashboard and Society Head pages read them. |
| Search | Plot numbers in any spelling (A-14, a14, A 14, a bare number in every block), blocks, facilities, coordinates (nearest plots within 400 m with distances); filters (block, size, status, built / vacant, development), sorting, pages of 25. |
| Plot page | Drawn map of the plot, its neighbours (houses darker), streets and facilities; status with source and confidence; nearest mosque, park, school, hospital, shops and gate with distances; plot facts; status history; save, share, open in 3D, Google Maps link. |
| Accounts and roles | Log in with checks and a lock after 5 wrong passwords; sign up (End User, or Society Head waiting for approval); pages for one role send others to log in. Kept in the browser until the backend exists (`src/lib/auth.js`), with three demo accounts. |
| Society Head | Overview with real counts per block and status; status updates with the rule that Sold cannot go back to Available, a note, a log, and the change shown at once on the map and plot page; records: list, add (number must be new, boundary GeoJSON checked and tested for overlap with every plot of the block), remove and restore with a reason. |
| Administrator | Overview; the real data sources (plan, block maps, OpenStreetMap, Google measurements, building footprints, nalla trace, sample status, assumed heights, Sentinel-2 to come, textures) with verify / flag / pending and an audit trail; user accounts (approve, disable, change role, reset password, add, remove). |
| Trends | The chart is marked as sample values until the model exists; next to it the real built share per block (2023 footprints). |
| Home | Real figures (plots, plots built, facilities), real plots in the search preview, pictures of the real 3D map (`tools/make_previews.py`), the forecast marked as sample. |
| 3D map page | Same controls as before as a React page; the map is created on open and freed on leave (`dispose()`), the animated background pauses while it is open; a "Plot details" link in the side panel; Cesium token from `VITE_CESIUM_TOKEN`. |
| Map additions | Plot numbers painted on vacant plots and white survey pillars at their corners when the camera is close (turned to read upright from the camera); running fountains in the parks and on the roundabout monuments (GPU particles); people walking on the park paths; two-layer moving ripples on the lakes and the nalla; icons on facility labels; an opening flight down to the society. |
| Data | Dispensaries where the newer plan has them: `emap_dispensaries` in `make_data.py` takes the plan's green DIS sites that no older site covers (Block D north, 1.1 kanal) and `DIS_MEASURED` the one the plan reader merges into its neighbours (Block C, 21 x 27 m between the primary school and the commercial area, measured on the plan); they are claimed before the older outlines, so the older Commercial Centre C no longer covers the site (it had been dropped as a sliver). `tools/align_roads.py` now centres the boulevard's carriageways on the white dashed lane line where it shows (paint 28 grey levels brighter than the road's own asphalt, within 2 m of the asphalt band's centre): stations moved up to 1.9 m (way 376583797 by 0.8 m on average). |

Checks: every page loads with no script error; logging in as each role, a status update, a duplicate record and the role guard were tested in headless Chrome; the map page loads, selects, goes full screen and back, opens the Cesium tab without a token, and is freed and rebuilt when left and reopened.

## 14. Open items waiting on Taha

- More screenshots of flaws, if he finds any after the 14 November fix. Fix those first and update this file.
- Cesium ion token.
- Real plot records from the society, if he can get them.
- Open pull request #4 (feature/3d-map into main) for Mursaleen, and tell him the pages are React now (he may have local changes to the old HTML pages).
- Test on his own laptop and phone (the Graphics button: Auto / High / Fast).
