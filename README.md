# EASE MPC Echograms

Export an image for every listening position at 500, 1000 and 2000 Hz from an EASE MPC file. Seats are detected automatically. Each image includes a Haas diagram overlay and highlights region-D candidates.

Requires Python 3.10 or newer.

```sh
git clone https://github.com/Jordi-14/AE-ETSETB-ease-mpc-echograms.git
cd AE-ETSETB-ease-mpc-echograms
python3 -m pip install -r requirements.txt
python3 mpc_echograms.py "/path/to/file.mpc"
```

Images are saved beside the MPC in `<file name>_echograms`, along with CSV data and a summary.

Tested with EASE 4.4 MPC files. The Haas boundary is approximate; check borderline cases in EASE Probe.
