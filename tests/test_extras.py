import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from mpc_echograms.cli import export, main
from mpc_echograms.extras import export_models, export_all_reflections, export_combined_echograms, export_interactive
from mpc_echograms.plotting import _id_slug
from mpc_echograms.reader import Dataset, Seat, Source, Ray
from test_multiview import sample


class ExtraExportTests(unittest.TestCase):
    def test_mirror_ids_have_readable_distinct_filenames(self):
        self.assertEqual(_id_slug(1), '001')
        self.assertEqual(_id_slug(0xffffffff), 'mirror_001')
        self.assertNotEqual(_id_slug(1), _id_slug(0xffffffff))

    def test_glb_contains_saved_paths_and_valid_accessors(self):
        d = sample()
        with tempfile.TemporaryDirectory() as tmp:
            files = export_models(d, Path(tmp), [500, 1000, 2000])
            self.assertEqual({p.name for p in files}, {'all_ray_paths.glb', 'D_ray_paths.glb'})
            for path in files:
                raw = path.read_bytes()
                self.assertEqual(struct.unpack_from('<4sII', raw), (b'glTF', 2, len(raw)))
                size, tag = struct.unpack_from('<I4s', raw, 12)
                self.assertEqual(tag, b'JSON')
                doc = json.loads(raw[20:20+size])
                self.assertEqual(doc['asset']['version'], '2.0')
                ids = [i for m in doc['meshes'] for i in m['extras']['ray_ids']]
                self.assertEqual(ids, [2] if path.name.startswith('D_') else [1, 2, 3])
                for mesh in doc['meshes']:
                    prim = mesh['primitives'][0]
                    self.assertEqual(prim['mode'], 1)
                    self.assertEqual(doc['accessors'][prim['attributes']['POSITION']]['count'] % 2, 0)
                binary_size, binary_tag = struct.unpack_from('<I4s', raw, 20+size)
                self.assertEqual(binary_tag, b'BIN\0')
                self.assertLessEqual(doc['buffers'][0]['byteLength'], binary_size)
                for view in doc['bufferViews']:
                    self.assertLessEqual(view['byteOffset']+view['byteLength'], binary_size)

    def test_models_without_D_do_not_create_fake_D_model(self):
        d = sample()
        d = Dataset(d.path, d.seats, d.sources, (d.rays[0], d.rays[2]), d.frequencies, '')
        with tempfile.TemporaryDirectory() as tmp:
            files = export_models(d, Path(tmp), [500])
            self.assertEqual([p.name for p in files], ['all_ray_paths.glb'])

    def test_empty_dataset_does_not_create_invalid_glb(self):
        d = sample()
        d = Dataset(d.path, d.seats, d.sources, (), d.frequencies, '')
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(export_models(d, Path(tmp), [500]), [])
            self.assertFalse(list(Path(tmp).iterdir()))

    def test_all_reflections_include_no_D_seat_and_all_saved_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = export_all_reflections(sample(), Path(tmp), 50, combined_pdf=True)
            self.assertEqual(len([p for p in files if p.suffix == '.png']), 2)
            self.assertTrue((Path(tmp)/'all_reflections.pdf').read_bytes().startswith(b'%PDF'))
            import csv
            with (Path(tmp)/'all_ray_paths.csv').open() as f:
                rows = list(csv.DictReader(f))
            self.assertEqual([int(r['ray_id']) for r in rows], [1, 2, 3])

    def test_combined_pdf_handles_more_than_three_bands(self):
        d = sample()
        frequencies = (500, 1000, 2000, 4000)
        rays = tuple(Ray(r.id, r.seat_id, r.source_id, r.order, r.arrival_ms,
                         (*r.levels_db, r.levels_db[-1]), r.reflection_points, r.face_labels) for r in d.rays)
        d = Dataset(d.path, d.seats, d.sources, rays, frequencies, '')
        with tempfile.TemporaryDirectory() as tmp:
            files = export_combined_echograms(d, Path(tmp), list(frequencies))
            self.assertEqual(len(files), 1)
            self.assertTrue(files[0].read_bytes().startswith(b'%PDF'))

    @unittest.skipUnless(importlib.util.find_spec('plotly'), 'Optional Plotly not installed')
    def test_interactive_is_offline_and_separates_source_receiver_pairs(self):
        d = sample()
        with tempfile.TemporaryDirectory() as tmp:
            files = export_interactive(d, Path(tmp), [500, 1000, 2000])
            text = files[0].read_text(encoding='utf-8')
            self.assertIn('plotly.js', text.lower())
            self.assertNotIn('<script src="https://', text)
            self.assertIn('Source S / Seat A', text)
            self.assertIn('Source S / Seat B', text)
            self.assertIn('no direct reference; unclassifiable', text)
            self.assertIn('Recorded paths only', text)

    @unittest.skipUnless(importlib.util.find_spec('plotly'), 'Optional Plotly not installed')
    def test_interactive_escapes_labels_in_script(self):
        d = sample()
        label = '</script><script>window.BAD_LABEL=1</script>'
        d = Dataset(d.path, (Seat(1, label, d.seats[0].position), *d.seats[1:]),
                    d.sources, d.rays, d.frequencies, '')
        with tempfile.TemporaryDirectory() as tmp:
            path, = export_interactive(d, Path(tmp), [500])
            text = path.read_text(encoding='utf-8')
            self.assertNotIn(label, text)
            self.assertIn('BAD_LABEL', text)

    def test_manifest_rerun_cleans_extras_but_preserves_unrelated_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'input.mpc'
            p.write_bytes(b'fixture')
            d = sample(p)
            d = Dataset(p, d.seats, d.sources, d.rays, d.frequencies, hashlib.sha256(p.read_bytes()).hexdigest())
            out = Path(tmp)/'output'
            def images(dataset, staging, **kwargs):
                image = staging/'chart.png'; image.write_bytes(b'chart'); return [image]
            with patch('mpc_echograms.plotting.export_images', images):
                m = export(d, out, [500], 50, models=True)
                self.assertIn('all_ray_paths.glb', m['generated_files'])
                (out/'notes.txt').write_text('keep')
                export(d, out, [500], 50)
                self.assertFalse((out/'all_ray_paths.glb').exists())
                self.assertEqual((out/'notes.txt').read_text(), 'keep')

    def test_all_outputs_cli_requests_geometry_and_all_exporters(self):
        with patch('mpc_echograms.cli.read_mpc', return_value=sample()) as read, \
             patch('mpc_echograms.cli.export', return_value={'image_count': 6, 'multiviews': None}) as write:
            self.assertEqual(main(['example.mpc', '--all-outputs']), 0)
            self.assertTrue(read.call_args.kwargs['include_geometry'])
            for key in ['multiviews', 'all_reflections', 'combined_pdf', 'interactive', 'models']:
                self.assertTrue(write.call_args.kwargs[key])
