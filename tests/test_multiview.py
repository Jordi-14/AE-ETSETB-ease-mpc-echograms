import csv
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from mpc_echograms.reader import Dataset, Seat, Source, Ray, MPCError, _reflection_geometry
from mpc_echograms.multiview import select_d_paths, export_multiviews
from mpc_echograms.context import read_context_edges
from mpc_echograms.cli import export


def sample(path=Path('example.mpc')):
    return Dataset(path, (Seat(1, 'A', (0., 10., 1.2)), Seat(2, 'B', (4., 10., 1.2))),
                   (Source(1, 'S', (0., 0., 1.6)),),
                   (Ray(1, 1, 1, 0, 10., (80., 80., 80.)),
                    Ray(2, 1, 1, 1, 70., (70., 72., 71.), ((-2., 5., 3.),), ('F9',)),
                    Ray(3, 2, 1, 0, 12., (80., 80., 80.))),
                   (500, 1000, 2000), '')


class GeometryTests(unittest.TestCase):
    def test_labelled_nodes_and_binary_false_positive(self):
        buf = bytearray(358)
        buf += b'\xff\xffF3' + b'\0' * 16  # Not a length-prefixed label.
        buf += struct.pack('<H', 3) + b'F12' + b'\0' * 4 + struct.pack('<fff', 1, 2, 3)
        points, labels = _reflection_geometry(bytes(buf), 0, len(buf), 1)
        self.assertEqual(points, ((1., 2., 3.),))
        self.assertEqual(labels, ('F12',))
        with self.assertRaisesRegex(MPCError, 'expected 2'):
            _reflection_geometry(bytes(buf), 0, len(buf), 2)

    def test_bad_coordinate_rejected(self):
        buf = b'\0' * 358 + struct.pack('<H', 2) + b'F1' + b'\0' * 4 + struct.pack('<fff', 1, 2, float('nan'))
        with self.assertRaisesRegex(MPCError, 'Non-finite'):
            _reflection_geometry(buf, 0, len(buf), 1)

    def test_ascii_dxf_uses_modelspace_and_offset(self):
        text = '0\nSECTION\n2\nBLOCKS\n0\n3DFACE\n10\n999\n0\nENDSEC\n0\nSECTION\n2\nENTITIES\n'
        text += '0\n3DFACE\n10\n0\n20\n0\n30\n0\n11\n2\n21\n0\n31\n0\n12\n0\n22\n2\n32\n0\n13\n0\n23\n2\n33\n0\n'
        text += '0\nENDSEC\n0\nEOF\n'
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'context.dxf'
            p.write_text(text)
            edges = read_context_edges(p, .9)
        self.assertEqual(len(edges), 3)
        self.assertTrue(all(v[2] == .9 and v[0] != 999 for edge in edges for v in edge))


    def test_closed_3D_polyline_context(self):
        pairs = [(0, 'SECTION'), (2, 'ENTITIES'), (0, 'POLYLINE'), (70, '9')]
        for x, y in [(0, 0), (2, 0), (2, 2), (0, 2)]:
            pairs += [(0, 'VERTEX'), (10, str(x)), (20, str(y)), (30, '1')]
        pairs += [(0, 'SEQEND'), (0, 'ENDSEC'), (0, 'EOF')]
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'polyline.dxf'
            p.write_text(''.join(f'{code}\n{value}\n' for code, value in pairs))
            edges = read_context_edges(p)
        self.assertEqual(len(edges), 4)
        self.assertTrue(all(point[2] == 1 for edge in edges for point in edge))


class MultiviewTests(unittest.TestCase):
    def test_path_appears_once_with_largest_selected_band_excess(self):
        data = sample()
        rows = select_d_paths(data, [500, 1000, 2000])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['worst_frequency_Hz'], 1000)
        self.assertAlmostEqual(rows[0]['max_excess_dB'], 3.)
        self.assertEqual(len(rows[0]['D_bands']), 3)
        self.assertEqual(rows[0]['points'][1], (-2., 5., 3.))
        self.assertAlmostEqual(select_d_paths(data, [500])[0]['max_excess_dB'], 1.)

    def test_direct_reference_is_per_source(self):
        d = sample()
        second = Source(2, 'other', (0., 0., 1.6))
        rays = d.rays + (Ray(4, 1, 2, 0, 10., (100., 100., 100.)),
                         Ray(5, 1, 2, 1, 70., (80., 80., 80.), ((-2., 5., 3.),), ('F9',)))
        data = Dataset(d.path, d.seats, (*d.sources, second), rays, d.frequencies, d.sha256)
        self.assertEqual([p['source_id'] for p in select_d_paths(data, [1000])], [1])

    def test_no_direct_cannot_be_claimed_safe(self):
        d = sample()
        d = Dataset(d.path, d.seats, d.sources, d.rays[1:2], d.frequencies, d.sha256)
        with tempfile.TemporaryDirectory() as tmp:
            files, info = export_multiviews(d, Path(tmp), [500], dpi=50)
            self.assertEqual(info['view_count'], 0)
            self.assertEqual(info['skipped'][0]['reason'], 'no-direct-reference')
            self.assertFalse(list(Path(tmp).glob('*.png')))

    def test_skip_no_D_seats_and_clean_only_managed_files_on_rerun(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'input.mpc'
            p.write_bytes(b'fixture')
            d = sample(p)
            d = Dataset(p, d.seats, d.sources, d.rays, d.frequencies, hashlib.sha256(p.read_bytes()).hexdigest())
            output = Path(tmp) / 'results'
            def fake_images(dataset, staging, **kwargs):
                image = staging / 'chart.png'
                image.write_bytes(b'chart')
                return [image]
            with patch('mpc_echograms.plotting.export_images', fake_images):
                m = export(d, output, [500, 1000, 2000], 50, multiviews=True)
                self.assertEqual(m['multiviews']['view_count'], 1)
                self.assertEqual(m['multiviews']['skipped'][0]['seat_id'], 2)
                self.assertEqual(m['multiviews']['colour_range_dB'], [0, 3.])
                self.assertEqual(len(list(output.glob('*_D_multiview.png'))), 1)
                with (output / 'D_ray_paths.csv').open() as stream:
                    self.assertEqual(len(list(csv.DictReader(stream))), 1)
                note = output / 'my-note.txt'
                note.write_text('keep')
                export(d, output, [500, 1000, 2000], 50)
                self.assertFalse(list(output.glob('*_D_multiview.*')))
                self.assertFalse((output / 'D_ray_paths.csv').exists())
                self.assertEqual(note.read_text(), 'keep')


if __name__ == '__main__':
    unittest.main()
