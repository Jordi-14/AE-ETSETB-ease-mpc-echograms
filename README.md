# EASE MPC Echograms

Export one echogram per listening position at 500, 1000 and 2000 Hz from an EASE MPC file. Seats are detected automatically. Each image includes a Haas diagram overlay and highlights region-D candidates.

Requires Python 3.10 or newer.

```sh
git clone https://github.com/Jordi-14/AE-ETSETB-ease-mpc-echograms.git
cd AE-ETSETB-ease-mpc-echograms
python3 -m pip install -r requirements.txt
python3 mpc_echograms.py "/path/to/file.mpc"
```

Results are saved beside the MPC in `<file name>_echograms`, with `arrivals.csv` and `summary.json`. The input MPC is never modified. Use `--output DIR` to choose another destination or `--frequencies 500 1000 2000` to select bands.

## Ray multiviews

Add `--multiviews` to also generate the remaining region-D paths:

```sh
python3 mpc_echograms.py "/path/to/file.mpc" --multiviews
```

Each seat/source pair with D candidates gets one multiview in **PNG and PDF**, showing:

- 3D perspective, plan XY, side elevation YZ and front elevation XZ; Z stays vertical in elevations.
- Every D-candidate path once, coloured by its **largest excess above the Haas boundary** across the selected frequency bands.
- A shared colour scale across all seats and sources, with a dashed direct path and marked reflection points.

Seats with no D candidates are skipped. Seats without a saved direct arrival are skipped as unclassifiable, not reported as free of echoes. The manifest records the reason. `D_ray_paths.csv` lists every candidate's source/seat/path IDs, arrival time, delay, maximum excess, frequency bands, face sequence and XYZ path coordinates. Coincident projected segments can overlap.

Multiview geometry is decoded from the MPC itself. No DXF is required. To add a room wireframe:

```sh
python3 mpc_echograms.py "/path/to/file.mpc" --multiviews \
  --context-dxf "/path/to/room.dxf"
```

The DXF is a visual backdrop only. Its coordinates and metre units must match the MPC. If its Z datum differs, `--context-z-offset 0.9` adds 0.9 m to the **DXF only**, without moving the recorded rays. The context reader accepts model-space `3DFACE` and closed 3D `POLYLINE` entities in ASCII DXF; blocks, inserts, 2D entities and binary DXF are not supported. It does not repair or transform the model automatically.

## Interpretation and supported files

Tested with EASE 4.4 MPC exports. The reader supports an observed binary layout, not a published AFMG interchange specification. Multiviews additionally require the observed named `F<number>` reflection-node layout. Geometry is checked against reflection order, finite coordinates and propagation-time consistency; unsupported geometry is rejected. Run without `--multiviews` when only the echogram layout is supported.

The Haas boundary approximates the diagram in the ETSETB theatre assignment (`theatre design.pdf`, page 4), over **0–100 ms after the direct arrival**. It is not a universal echo audibility standard. Each band is normalised to its own direct sound; excess is the reflection's relative level minus the diagram boundary at that delay. Check borderline cases in EASE Probe. Counts describe individual paths, without time-bin energy summation or a synthetic reverberation tail. A multiview shows ray paths, not sound-energy coverage.

Reruns replace only files recorded in the previous manifest, preserving unrelated files. Reusing an output directory generated from another MPC is rejected. Rerunning without `--multiviews` removes the previously managed multiview files.

## Checks

```sh
python3 -m unittest discover -s tests -v
```

Tests use synthetic geometry and results; no project MPC, DXF, private coordinates or generated plots are included in this repository.
