# Observed native project layout

This describes the supported EASE 4.4 files, not an AFMG interchange specification. The reader rejects other headers and validates all referenced vertices. Synthetic fixtures in `tests/test_project.py` exercise the format without distributing real projects.

All numerical fields below are little-endian. Short strings use a uint16 byte length and Windows-1252 bytes. Unsupported encodings/lengths fail explicitly.

## Common table header

The 30-byte header starts with `EASE`, uint16 values `(3, 1, 20)`, and a two-byte table tag. Record-version and in-memory structure-size fields are checked per table. The uint32 record count is at offset 18; the structure-size field is at 22. The value at offset 26 is 31. The structure-size field is **not** the serialized disk-record length.

| Tag | Record version | Structure-size field |
| --- | --- | --- |
| `vt` | 1 | 48 |
| `fc` | 2 | 220 |
| `st` | 1 | 304 |

## Vertices (`.fvt`)

After the header are `count + 1` records of 40 bytes, including dummy index zero. Coordinates are three float32 values at offset 12 within each record. Face vertex references use indices 1 through `count`. Other record fields are not interpreted. Coordinates are displayed in the MPC's metre system; no scale fitting is performed.

## Faces (`.ffc`)

After the header and a 100-byte dummy entry, each face has:

1. An opaque 150-byte fixed prefix.
2. Front material string, uint32 index and uint16 reference flags.
3. Rear material string, uint32 index and uint16 reference flags.
4. Two texture strings, each followed by an uninterpreted uint32 value.
5. Float32 stored area, uint32 packed colour, eight reserved bytes, uint32 boundary vertex count.
6. Uint16 marker 1, uint32 closed-ring count (`boundary count + 1`), uint32 zero, then the closed ring of uint32 vertex IDs. First and last IDs must match.

A 128-byte zero trailer follows the last face. Face IDs are their one-based table positions (`F1`, `F2`, …). RGB colour uses the low three bytes of the packed colour. Polygon area/normal are independently calculated from vertices. The raw flags word at fixed-prefix offset 136 is preserved; bit 1 (mask 2) identifies the observed two-sided faces when calculating total surface area. Other bits are not assigned meanings.

Concave polygons use projected ear clipping. Unsupported triangulations get an explicit warning and no invented fill; their original boundary remains available. Mirrored face references ending in `*` use the supported YZ mirror plane when matching MPC nodes. The viewer adds mirrored polygons referenced by the MPC; it does not infer unobserved symmetric geometry from undecoded room settings.

## Listener seats (`.fst`)

The header is followed by `count + 1` entries including index zero. Each entry contains label and mirror-label strings, then a 292-byte tail. Coordinates are float32 values at tail offset 8. Other tail fields are not interpreted. MPC positions take precedence for rendering.

## Deliberately undecoded data

`.frd`, `.fld`, `.far` and `.fwm` companion presence, hashes and declared counts are recorded. Their room settings, sources, audience polygons and native material coefficient arrays are not decoded. In particular, zero-filled material catalogue metadata must not be interpreted as valid zero coefficients. External material files may be needed; explicit coefficient curves can instead be supplied by configuration with their source stated.

## Validation scope

Compatibility tests a saved reflection point against its named polygon at an explicit metre tolerance. It detects missing faces, plane distance and points outside polygon boundaries. Listener coordinates are compared independently by ID. It cannot prove that unseen geometry, source settings or materials match the MPC, and does not check complete ray segments for intervening surfaces. Geometry measurements are boundary integrals, not an acoustic simulation or an independent proof of a sealed room.
