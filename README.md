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

The HTML viewer works offline in a browser. GLB files contain **line primitives**, so use a glTF viewer supporting lines. These models contain recorded paths, not reconstructed walls. Their coordinates are in metres; GLB converts MPC `(X,Y,Z)` to glTF `(X,Z,-Y)` to preserve vertical orientation.

## Optional room context

A matching ASCII DXF can be added as a wireframe backdrop:

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
