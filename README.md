# EASE MPC Echograms

Export echograms and recorded ray paths from EASE MPC impact files. Sources and receivers are detected from the file, including mirrored receivers such as `1*`. No DXF is required.

Requires Python 3.10+. The default export uses Matplotlib. The optional offline interactive viewer also uses Plotly.

## Quick start

```sh
git clone https://github.com/Jordi-14/AE-ETSETB-ease-mpc-echograms.git
cd AE-ETSETB-ease-mpc-echograms
python3 -m pip install -r requirements.txt
python3 mpc_echograms.py "/path/to/project.mpc"
```

On Windows, use `py` instead of `python3` in these commands. Quote paths containing spaces. Use the same Python interpreter for installation and execution.

The default produces one PNG per source, receiver and selected frequency, plus `arrivals.csv` and `summary.json`. Default bands are **500, 1000 and 2000 Hz**. Results go beside the MPC in `<name>_echograms`; use `--output DIR` to choose another folder. The source MPC is never modified.

## Generate everything

Install the interactive dependency and enable every export:

```sh
python3 -m pip install -r requirements-interactive.txt
python3 mpc_echograms.py "/path/to/project.mpc" --all-outputs
```

Windows:

```powershell
py -m pip install -r requirements-interactive.txt
py mpc_echograms.py "C:\path\to\project.mpc" --all-outputs
```

This includes the default echograms and:

| Option | Output |
| --- | --- |
| `--multiviews` | PNG/PDF D-only ray views, plus `D_ray_paths.csv`. |
| `--all-reflections` | PNG/PDF views of every saved path, plus `all_ray_paths.csv`. |
| `--combined-pdf` | `echograms.pdf`, with up to three bands per receiver/source page; combined PDFs for enabled ray views. |
| `--interactive` | Self-contained `ray_viewer.html`: rotate/zoom, choose a source/receiver pair, switch between all paths and D candidates. Requires Plotly. |
| `--models` | `all_ray_paths.glb` and, when D candidates exist, `D_ray_paths.glb`. No Plotly required. |
| `--all-outputs` | All the options above. |

Options can be combined independently:

```sh
python3 mpc_echograms.py "/path/to/project.mpc" --multiviews --combined-pdf
python3 mpc_echograms.py "/path/to/project.mpc" --all-reflections --models
python3 mpc_echograms.py "/path/to/project.mpc" --frequencies 500 1000 --dpi 220
```

Every multiview contains **3D, XY, YZ and XZ** views, with Z vertical in elevations. D views show each physical path once, coloured by its largest excess across the selected bands, using a shared scale. All-reflection views use colour for reflection order. Coincident projected paths can overlap.

D-only views skip receiver/source pairs without D candidates. A pair with no saved direct arrival is skipped as **unclassifiable**, not reported as free of echoes. The manifest records why. All-reflection views include every declared pair, even one with no saved paths.

The HTML viewer works offline in a browser. It has source/receiver selection, all/D paths, frequency, order/relative-level/Haas-excess colours, category filters, and path inspection. GLB files contain **line primitives**, so use a glTF viewer supporting lines. The GLBs contain recorded paths, not reconstructed walls. Their coordinates are in metres; GLB converts MPC `(X,Y,Z)` to glTF `(X,Z,-Y)` to preserve vertical orientation.

## Optional: identify openings and audience

Tell the viewer which faces represent openings or audience surfaces by saving a **JSON configuration file** and passing it with `--project-config`. These tags are optional: without a configuration, the tool does not automatically identify either category.

### Tag faces by their EASE IDs (works with the MPC alone)

Create `categories.json`, replacing the example IDs with your own EASE face numbers:

```json
{
  "categories": {
    "openings": {"faces": ["F2", "F3"]},
    "audience": {"faces": ["F4", "F5"]}
  }
}
```

Then generate the viewer:

```sh
python3 mpc_echograms.py "/path/to/results.mpc" --interactive --project-config categories.json
```

Windows:

```powershell
py mpc_echograms.py "C:\path\to\results.mpc" --interactive --project-config categories.json
```

You can copy and edit [examples/categories-only.json](examples/categories-only.json). No absorption/scattering data is needed to use categories. You may supply just one category, omit an unused `faces`/`materials` list, or leave it empty.

### Tag faces by material name (requires the native project)

If the same material identifies all your openings or seating surfaces, use its EASE material name instead of listing every face:

```json
{
  "categories": {
    "openings": {"materials": ["Example open boundary"]},
    "audience": {"materials": ["Example seating"]}
  }
}
```

Replace these names with the actual material names, then run:

```sh
python3 mpc_echograms.py "/path/to/results.mpc" --project "/path/to/project.frd" --interactive --project-config categories.json
```

Material matching needs `--project` because an MPC alone does not provide the face material table. Matching uses the front **or** rear material name, ignoring letter case; it does not use partial names or wildcards. You can inspect the face selector in the viewer or `project_faces.csv` to find IDs and material names. AutoCAD layer names and EASE audience-area objects are not used automatically.

### Tag faces by colour (requires the native project)

If you gave each CAD layer a different colour and retained those colours in EASE, you can classify the faces by their **saved EASE face colour**, independently of their acoustic materials:

```json
{
  "categories": {
    "openings": {"colors": ["#FF0000", "#FFFF00"]},
    "audience": {"colors": ["#0000FF"]}
  }
}
```

Replace these illustrative colours with your own. Run with both `--project` and `--project-config`, as in the material-name example. You can copy [examples/categories-by-colour.json](examples/categories-by-colour.json).

The JSON key is **`colors`**. Each item can use any of these equivalent formats:

| Format | Example: red |
| --- | --- |
| Hex RGB | `"#FF0000"` |
| RGB byte triple | `[255, 0, 0]` |
| EASE/Windows colour number | `255` |

RGB triples must be nested inside the colour list: `"colors": [[255, 0, 0]]` means red. By contrast, `"colors": [255, 0, 0]` is a list of three EASE colour numbers. You can mix formats, for example `"colors": ["#FF0000", [0, 255, 0], 16711680]` selects red, green and blue.

EASE numbers use **R + 256×G + 65536×B**. They are not AutoCAD ACI indices or ordinary `0xRRGGBB` numbers. For example, EASE blue is `16711680`, while its hex RGB is `"#0000FF"`.

To find the correct value, inspect a face in the viewer: it shows a colour swatch, hex, RGB and EASE number. The same values appear as `colour_hex`, `colour_rgb` and `colour_ease` in `project_faces.csv`. Matching is exact, with no nearest-colour guessing.

This does not recover layer names. It works as a layer proxy only when the relevant layers have distinct, consistent face colours. If EASE changes those colours or two layers share a colour, check your rules. Changing a material alone does not affect a colour rule.

### Combine rules and use the filters

You can combine face IDs, materials and colours in the same category:

```json
{
  "categories": {
    "openings": {"faces": ["F2"], "materials": ["Example open boundary"], "colors": ["#FF0000"]},
    "audience": {"faces": ["F4"], "materials": ["Example seating"], "colors": ["#0000FF"]}
  }
}
```

A face matches if its ID **or** either material name **or** its colour matches. A base ID such as `F2` also tags its mirrored `F2*`; listing only `F2*` tags that mirrored face alone. Colour rules also apply to mirrored faces. Check ID-based rules again after reimporting or renumbering the room.

If any bounce along a path touches a tagged face, the **whole path** receives that category. A path can be tagged as both opening-dependent and audience-dependent. In `ray_viewer.html`, use **Hide opening-dependent paths** and **Hide audience paths** independently. Opening-dependent paths remain grey/dashed when shown. All saved paths remain in the data; these controls do not delete rays, recalculate acoustics, or replace the audience with a scattering simulation. The original echograms/arrival tables retain their MPC results, and `path_categories.csv` records the tags when a configuration is supplied.

## Native EASE project support (1.3)

Use a matching EASE project to reconstruct room polygons and associate saved reflections with native face IDs and material names:

```sh
python3 mpc_echograms.py "/path/to/results.mpc" \
  --project "/path/to/project.frd" --interactive
```

`--project` also accepts a folder containing one supported room project. Speaker-model `.frd` files are excluded from automatic selection. If several room projects exist, select the `.frd` explicitly. Required companions are same-basename `.fvt` and `.ffc`; `.fst` is optional. All inputs are read-only.

The reader supports the **observed EASE 4.4 native vertex, face and listener layouts**. It validates record sizes, closed polygon lists, vertex references, finite coordinates and file trailers; unexpected layouts fail instead of guessing. Concave faces use ear-clipping triangulation. Faces that cannot be safely triangulated remain available as wireframe with a warning.

Extra outputs:

| File | Contents |
| --- | --- |
| `project_room.json` | Native vertices, polygons, material names, geometry measurements, supplied curves and provenance. |
| `project_faces.csv`, `project_vertices.csv` | Face and vertex lookup tables. |
| `reflection_faces.csv` | Each saved bounce linked to its project face/material snapshot. |
| `project_compatibility.json` | Named-face checks for saved reflection points; listener-coordinate differences and limitations. |
| `path_categories.csv` | Explicit opening/audience tags, preserving every saved path. |

The viewer adds wireframe/translucent surfaces, clickable faces, a face selector, and a path selector that highlights the route and its reflecting polygons. Face details include area, vertex-order normal, planarity deviation and front/rear material names. All rendered source/receiver positions and saved levels remain from the **MPC**, even when the project is older.

Compatibility checks test each saved reflection point against the **interior/boundary of its named polygon**, not just the plane. The default tolerance is 0.01 m; change it with `--project-tolerance`. `--project-strict` rejects known reflection-point or listener-position mismatches. Matching sampled points does **not** prove unobserved geometry, whole-path visibility, material settings, or the entire project revision matches. Mirrored `F…*` references are checked at the supported YZ mirror plane; the viewer adds their referenced mirrored polygons.

### Material data and project-specific categories

Native face material names are decoded. **Native acoustic curves, source tables, audience-area tables and room-settings tables are not decoded in this release.** Their presence/counts are reported where available. Some projects reference external material files absent from the copy. Zero-filled catalogue metadata is never interpreted as zero absorption or scattering.

For opening/audience tags, follow [Optional: identify openings and audience](#optional-identify-openings-and-audience) above. To supply coefficient curves as well, use the same `--project-config` file; [examples/project-config.json](examples/project-config.json) contains both categories and optional curves:

```sh
python3 mpc_echograms.py "/path/to/results.mpc" \
  --project "/path/to/project.frd" --project-config config.json --all-outputs
```

Categories match face IDs or front/rear material names. No theatre-specific IDs, layer names or guessed semantics are built into the code. Filtering opening/audience paths changes the viewer only; original echograms and arrival tables retain the saved MPC data. Missing direct sound remains unclassifiable. Audience filtering is not a scattering simulation.

Material curves supplied in the configuration need increasing frequencies, coefficients in [0,1], and a `source` string. They are shown with their provenance when a face is inspected. They are **not** asserted to be the coefficients used by the MPC. Missing curves are displayed as unavailable. The project material snapshot is always labelled separately from MPC results.

Native geometry, compatibility and categories are recorded in `summary.json`. Project/configuration hashes are rechecked before output installation, and existing managed-output safeguards apply to all new artifacts. Do not distribute private project files with a public code repository.

## Optional room context

A matching ASCII DXF can alternatively be added as a wireframe backdrop (`--project` and `--context-dxf` are mutually exclusive):

```sh
python3 mpc_echograms.py "/path/to/project.mpc" --all-outputs --context-dxf "/path/to/room.dxf"
```

The context is used in static ray views and the interactive viewer, not the GLB ray-only models. It is visual context, not a visibility or geometry validation. Coordinates and metre units must match the MPC. `--context-z-offset 0.9` adds 0.9 m to the DXF only.

The DXF reader accepts model-space `3DFACE` and closed 3D `POLYLINE` entities. Blocks, inserts, 2D entities and binary DXFs are not supported. No automatic repair or block transformation is performed.

## Compatibility and interpretation

The reader supports **observed EASE 4.x binary layouts tested with EASE 4.4 exports**, rather than a published AFMG interchange specification. It supports empty or populated mirror-name fields, YZ-mirrored entity coordinates and reflection labels such as `F2*`. Raw unsigned IDs are retained in data tables; filenames use readable names such as `mirror_001`.

Unexpected layouts are rejected instead of drawing unvalidated geometry. Ray exports additionally validate face-node counts, endpoint coordinates and propagation-time consistency. If an export contains unsupported reflection geometry, the basic echograms may still work without ray-view/model options.

The Haas boundary approximates the **ETSETB theatre assignment diagram**, over **0–100 ms after the direct arrival**. It is not a universal echo audibility standard. Each band is normalised to its own direct sound. Excess is the reflection's relative level minus the boundary at the same delay. Check borderline cases in EASE Probe.

Counts describe individual saved paths, without time-bin energy summation or an artificial reverberation tail. Delays outside the diagram are unclassified. Multiple sources are analysed separately. Only paths retained in the MPC can be shown; no new acoustic simulation is performed.

Reruns replace only artifacts listed in the previous manifest and preserve unrelated files. Turning options off removes their previously managed files. Output installation is staged; a failure or changing input leaves the previous export intact. Output folders generated from a different MPC are rejected.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

Fixtures are synthetic; no private MPCs, DXFs, coordinates or generated project images are included. Regression coverage includes mirror metadata, mirrored face labels, multiple-source normalisation, missing direct sound, optional exports, GLB structure and safe reruns. CI checks Windows, macOS and Linux with Python 3.10 and 3.12. Local project verification has been performed on macOS.
