"""Synthetic regression coverage for the offline echogram inspector payload."""
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest

from mpc_echograms.haas import TIMES, LEVELS
from mpc_echograms.reader import Dataset, Ray, Seat, Source
from mpc_echograms.viewer import export_viewer


@unittest.skipUnless(importlib.util.find_spec('plotly'), 'Optional Plotly not installed')
class EchogramInspectorTests(unittest.TestCase):
    def export(self, dataset):
        with tempfile.TemporaryDirectory() as tmp:
            path, = export_viewer(dataset, Path(tmp), [500, 1000])
            text = path.read_text(encoding='utf-8')
        payload = json.loads(re.search(r'<script id="reflection-data" type="application/json">(.*?)</script>', text, re.S)[1])
        return text, payload

    def sample(self):
        return Dataset(Path('synthetic.mpc'), (Seat(1, 'A', (0., 5., 1.)), Seat(2, 'No direct', (2., 5., 1.))),
                       (Source(1, 'S1', (0., 0., 1.)), Source(2, 'S2', (1., 0., 1.))),
                       (Ray(1, 1, 1, 0, 10., (80., 90.)),
                        Ray(2, 1, 1, 1, 70., (70., 82.), ((-1., 2., 2.),), ('F1',)),
                        Ray(3, 1, 2, 0, 15., (100., 110.)),
                        Ray(4, 1, 2, 1, 75., (90., 102.), ((-1., 2., 2.),), ('F1',)),
                        Ray(5, 2, 1, 1, 80., (60., 65.), ((-1., 2., 2.),), ('F1',))),
                       (500, 1000), 'synthetic-sha')

    def test_offline_inspector_follows_face_inspectors_and_embeds_haas(self):
        text, payload = self.export(self.sample())
        self.assertLess(text.index('<section class="inspect">'), text.index('id="echo-title"'))
        for control in ['echo-band', 'echo-download', 'echogram-plot', 'echo-summary']:
            self.assertIn('id="'+control+'"', text)
        self.assertNotIn('<script src="https://', text)
        self.assertEqual(payload['haas']['times_ms'], list(TIMES))
        self.assertEqual(payload['haas']['levels_db'], list(LEVELS))
        self.assertEqual(payload['title'], 'synthetic')
        self.assertEqual(payload['bands'], [500, 1000])

    def test_saved_values_and_per_pair_references_are_preserved(self):
        _, payload = self.export(self.sample())
        rays = {r['id']:r for r in payload['rays']}
        self.assertEqual(set(rays), {1, 2, 3, 4, 5})
        for ray_id in [2, 4]:
            self.assertEqual(rays[ray_id]['delay'], 60.)
            self.assertEqual(rays[ray_id]['metrics']['500']['level'], -10.)
            self.assertEqual(rays[ray_id]['metrics']['1000']['level'], -8.)
        missing = rays[5]
        self.assertIsNone(missing['delay'])
        self.assertIsNone(missing['metrics']['500']['level'])
        self.assertIsNone(missing['metrics']['500']['excess'])
        self.assertEqual(missing['metrics']['500']['absolute'], 60.)
        self.assertEqual(missing['metrics']['500']['zone'], 'no-direct-reference')


if __name__ == '__main__':
    unittest.main()
