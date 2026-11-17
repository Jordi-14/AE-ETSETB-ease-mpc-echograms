"""Regression cases for EASE image names and mirrored coordinate metadata."""
import struct
import unittest
from mpc_echograms.reader import _metadata, _reflection_geometry, MPCError


def record(entity_id, label, mirror_label, xyz, source=False):
    length_at = 20 if source else 8
    body = bytearray(length_at + 2)
    struct.pack_into('<I', body, 4, entity_id)
    name = label.encode('cp1252')
    struct.pack_into('<H', body, length_at, len(name))
    body.extend(name)
    mirror = mirror_label.encode('cp1252')
    body.extend(struct.pack('<H', len(mirror)) + mirror + b'\0' * 8)
    body.extend(struct.pack('<fff', *xyz))
    return struct.pack('<I', len(body)) + body


class MirrorMetadataTests(unittest.TestCase):
    def test_distinct_base_and_image_positions_and_names(self):
        payload = record(1, '1', '1*', (3.7, 22., 6.8)) + record(0xffffffff, '1', '1*', (3.7, 22., 6.8))
        seats = _metadata(payload, 2)
        self.assertEqual([s.label for s in seats], ['1', '1*'])
        self.assertAlmostEqual(seats[0].position[0], 3.7, places=5)
        self.assertAlmostEqual(seats[1].position[0], -3.7, places=5)
        self.assertEqual(seats[0].position[1:], seats[1].position[1:])

    def test_source_mirror_name_does_not_shift_coordinates(self):
        source, = _metadata(record(1, 'S1', 'S1*', (0., 0., 1.6), True), 1, True)
        self.assertEqual(source.label, 'S1')
        self.assertAlmostEqual(source.position[2], 1.6, places=5)

    def test_empty_mirror_name_keeps_original_layout(self):
        seat, = _metadata(record(1, 'L01', '', (0., 7.77, 1.46)), 1)
        self.assertEqual(seat.label, 'L01')
        self.assertAlmostEqual(seat.position[1], 7.77, places=5)

    def test_mirrored_face_label_keeps_point(self):
        payload = b'\0' * 358 + struct.pack('<H', 3) + b'F2*' + b'\0' * 4 + struct.pack('<fff', -7., 3., 2.)
        points, labels = _reflection_geometry(payload, 0, len(payload), 1)
        self.assertEqual(labels, ('F2*',))
        self.assertEqual(points, ((-7., 3., 2.),))

    def test_truncated_mirror_metadata_rejected(self):
        with self.assertRaises(MPCError):
            _metadata(record(1, '1', '1*', (3.7, 22., 6.8))[:-5], 1)
