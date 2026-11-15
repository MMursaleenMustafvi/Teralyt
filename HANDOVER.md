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

```powershell
cd C:\Users\Taha\Teralyt
python -m http.server 8000
```

Open `http://localhost:8000/map.html` and press Ctrl+F5. Opening the file directly does not work, because the page fetches GeoJSON and ES modules.

URL options: `?plot=B-12`, `?id=2500`, `?lm=121` (121 is the main gate), `?time=evening` or `?time=night`, `?ground=satellite`, `?view=earth`, `?audit=1`.

Machine quirks:

- `git` is at `C:\Program Files\Git\cmd` and may not be on PATH in a tool shell.
- **Use Python 3.12** (`C:\Users\Taha\AppData\Local\Programs\Python\Python312\python.exe`, the first `python` on PATH). Since 15 November 2026 Windows Application Control blocks shapely's DLL in Python 3.15 ("An Application Control policy has blocked this file"). Python 3.12 has shapely, numpy, pillow, matplotlib, scipy, scikit-image, opencv and playwright. Run the tools with `python -I`.
- `tools/shoot.py` takes headless screenshots with the installed Chrome and software rendering. Run one capture at a time. The page now loads in about 12 seconds.
- **Only one server may run on port 8000.** Windows lets several `python -m http.server 8000` processes share the port; the browser then reaches a dead one and shows `ERR_EMPTY_RESPONSE` ("localhost didn't send any data"). This happened on 13 November. Before starting a server, stop the old ones:

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'http\.server' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

How to check one spot after a change: regenerate, then load the page and fly to the spot, for example `python -I tools/shoot.py "http://127.0.0.1:8000/map.html?plot=A-1059" out.png --el "#stage"`, and look at the image. Taha reports flaws as close-up screenshots; the plot numbers in them locate the place, but **plot numbers shift after every regeneration**, so note the plot's latitude and longitude (shown in the side panel, or `lat` / `lon` in `plots.geojson`) before regenerating and search by `lat, lon` afterwards.

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

## 10. Known flaws and things not verified

- **Entrance-road commercial plots are trimmed**: the plan's rows along the Main Entrance Road (A-1 to about A-31, A-161 to A-194) are shallower than drawn because the real road with its service roads is wider than the plan draws it. Only the FDA's original plan can say where these plots really are.
- **26 plots still have no street within 6 m.** The largest group, A-244 to A-252 beside Park A-2, faces a plan street that Park A-2's old outline covers for its full width; others sit on streets along the society's outer edge, which the outline cuts to half width so they are not traced.
- **Lane positions**: lane lines are painted at the centre of each OpenStreetMap carriageway line; where that line is 1 to 2 m off the real asphalt (for example way 376583796 between the south-west roundabout and A/B), so are the lane lines.

- **emap.pk is a third-party redraw** with its watermark. Ask FDA for the original plan (CAD or PDF) and rerun with it.
- **Plot numbers are OCR**: 2.7% of plots have none and about 1.5% of the numbers are wrong (very small print, upside-down numbers made of 1, 6, 8, 9). Each plot says in `number_source` whether a neighbour confirms its number.
- **Sub-blocks are estimated**, not read.
- **About 70 plan plot cells are not placed** (was about 250): they lie mostly on a road as built (176 more are trimmed to the road edge instead). The rule since 15 November: a plan plot is kept, trimmed, while at least 35% of it remains. Each left-out cell is listed with its reason when `TERRALYT_DEBUG` is set.
- Block X site purposes come from the plan's labels only.
- The Cesium tab now draws the houses and the main gate; it is still untested with a token (terrain, World Imagery).
- `plot.html` and the top search bar still use the 60-plot sample in `assets/app.js` (Mursaleen's pages).
- Buildings are simple shapes; speed on real hardware untested; the footprint data is from about 2023.

## 11. Suggested order for the next work

1. Taha: look at the main road (gate to the north-east end), Block X and a few plots per block, in full screen; send screenshots of anything wrong.
2. Give the 26 plots without a street their street (Park A-2 row: trim Park A-2's old outline to the plan; streets along the society edge: trace them with the outline buffered outwards).
3. Re-centre the main carriageway lines on the asphalt where they are 1 to 2 m off (rerun `tools/align_roads.py` with a two-lane model), so the lane lines sit on the painted ones.
4. Improve number reading for Blocks A and X (a better OCR model) and read the sub-block names printed on the plan.
5. Replace emap.pk with the FDA's own plan if it can be obtained.
6. Open the pull request for Mursaleen.

## 12. Graphics

Done on 13 November 2026: the main gate model, houses with porches, roof stair rooms, tanks, boundary walls and gates, evening light with long shadows, bare scrub ground for unplotted land.

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

- More screenshots of flaws, if he finds any after the 14 November fix. Fix those first and update this file.
- Cesium ion token.
- Real plot records from the society, if he can get them.
- Whether to open the pull request for Mursaleen.
