"""Synthetic native-table fixtures; never use private project data in tests."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from mpc_echograms.project import read_project, audit_project, triangulate, polygon_geometry, point_on_face
from mpc_echograms.project_config import read_config, ray_categories
from mpc_echograms.reader import MPCError, Dataset, Seat, Source, Ray
from mpc_echograms.cli import export, main


def string(s):
    b=s.encode('cp1252');return struct.pack('<H',len(b))+b


def header(tag,count,version,size):
    return b'EASE'+struct.pack('<HHH',3,1,20)+tag+struct.pack('<HHHIII',version,0,0,count,size,31)


def fixture(root):
    base=Path(root)/'room'
    points=[(0.,0.,0.),(4.,0.,0.),(4.,4.,0.),(2.,2.,0.),(0.,4.,0.)]
    vb=header(b'vt',len(points),1,48)+bytes(40)
    for p in points:
        record=bytearray(40);struct.pack_into('<fff',record,12,*p);vb+=record
    base.with_suffix('.fvt').write_bytes(vb)
    prefix=bytearray(150);struct.pack_into('<I',prefix,136,6)
    fb=header(b'fc',1,2,220)+bytes(100)+prefix
    fb+=string('Test wall')+struct.pack('<IH',2,0)+string('Rear')+struct.pack('<IH',3,0)
    fb+=string('')+bytes(4)+string('')+bytes(4)
    fb+=struct.pack('<fI',12.,0x123456)+bytes(8)+struct.pack('<I',5)
    fb+=struct.pack('<HII',1,6,0)+struct.pack('<6I',5,1,2,3,4,5)+bytes(128)
    base.with_suffix('.ffc').write_bytes(fb)
    sb=header(b'st',1,1,304)
    for name,xyz in [('0',(0.,0.,0.)),('Listener',(1.,1.,1.))]:
        tail=bytearray(292);struct.pack_into('<fff',tail,8,*xyz);sb+=string(name)+string('')+tail
    base.with_suffix('.fst').write_bytes(sb)
    base.with_suffix('.frd').write_bytes(header(b'rd',1,1,884))
    return base


def dataset(path):
    path.write_bytes(b'synthetic impact fixture')
    return Dataset(path,(Seat(1,'Listener',(1.,1.,1.)),),(Source(1,'Source',(1.,0.,1.)),),
                   (Ray(1,1,1,0,10.,(80.,80.)),Ray(2,1,1,1,70.,(72.,73.),((1.,1.,0.),),('F1',))),
                   (500,1000),hashlib.sha256(path.read_bytes()).hexdigest())


class ProjectTests(unittest.TestCase):
    def test_project_basename_with_dots_preserves_companion_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=fixture(tmp)
            for p in list(Path(tmp).glob('room.*')):p.rename(Path(tmp)/('room.version.one'+p.suffix))
            project=read_project(Path(tmp)/'room.version.one.frd')
            self.assertEqual(project.base.name,'room.version.one')
            self.assertEqual(len(project.faces),1)

    def test_native_concave_polygon_names_colours_and_listeners(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=fixture(tmp);p=read_project(tmp);f=p.faces[0]
            self.assertEqual(len(p.vertices),5);self.assertEqual(f['label'],'F1');self.assertEqual(f['material_front'],'Test wall')
            self.assertEqual(f['material_rear'],'Rear');self.assertEqual(f['colour_rgb'],[86,52,18]);self.assertAlmostEqual(f['area_m2'],12.)
            pts=[p.vertices[i] for i in f['vertex_ids']]
            self.assertAlmostEqual(sum(polygon_geometry([pts[i] for i in t])[0] for t in f['triangles']),12.)
            self.assertFalse(point_on_face((2.,3.,0.),pts,.001)[0])
            self.assertTrue(p.unchanged());base.with_suffix('.fst').write_bytes(b'changed');self.assertFalse(p.unchanged())

    def test_rejects_truncation_bad_version_and_invalid_vertex_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=fixture(tmp);p=base.with_suffix('.fvt');original=p.read_bytes();p.write_bytes(original[:-1])
            with self.assertRaises(MPCError):read_project(base.with_suffix('.frd'))
            bad=bytearray(original);struct.pack_into('<H',bad,12,99);p.write_bytes(bad)
            with self.assertRaisesRegex(MPCError,'version'):read_project(base.with_suffix('.frd'))
            p.write_bytes(original);f=base.with_suffix('.ffc');bad=bytearray(f.read_bytes());struct.pack_into('<I',bad,len(bad)-128-24,999);f.write_bytes(bad)
            with self.assertRaisesRegex(MPCError,'vertex'):read_project(base.with_suffix('.frd'))

    def test_directory_selection_ignores_speaker_frd_and_rejects_ambiguity(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture(tmp);speaker=Path(tmp)/'speaker.frd';speaker.write_bytes(header(b'rd',1,0,604))
            self.assertEqual(read_project(tmp).base.name,'room')
            other=Path(tmp)/'other';other.mkdir();fixture(other)
            with self.assertRaisesRegex(MPCError,'found 2'):read_project(tmp)

    def test_audit_checks_polygon_interior_not_only_plane_and_mirror_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=read_project(fixture(tmp).with_suffix('.frd'));d=dataset(Path(tmp)/'r.mpc');a=audit_project(p,d)
            self.assertEqual(a['matched_nodes'],1)
            r=Ray(2,1,1,1,70.,(72.,73.),((2.,3.,0.),),('F1',))
            bad=Dataset(d.path,d.seats,d.sources,(d.rays[0],r),d.frequencies,d.sha256)
            self.assertEqual(audit_project(p,bad)['geometry_status'],'mismatch')
            mirror=Ray(2,1,1,1,70.,(72.,73.),((-1.,1.,0.),),('F1*',))
            self.assertEqual(audit_project(p,Dataset(d.path,d.seats,d.sources,(mirror,),d.frequencies,d.sha256))['matched_nodes'],1)

    def test_explicit_categories_and_curve_provenance_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=read_project(fixture(tmp).with_suffix('.frd'));d=dataset(Path(tmp)/'r.mpc');c=Path(tmp)/'config.json'
            c.write_text(json.dumps({'categories':{'openings':{'materials':['Test wall']}},'materials':{'Test wall':{'frequencies_Hz':[500,1000],'absorption':[.2,.3],'source':'Synthetic fixture'}}}))
            conf=read_config(c);self.assertEqual(ray_categories(d.rays[1],p,conf)['openings'],['F1'])
            c.write_text(json.dumps({'materials':{'Bad':{'frequencies_Hz':[1000,500],'absorption':[0,1],'source':'test'}}}))
            with self.assertRaises(MPCError):read_config(c)

    def test_export_reports_and_strict_mismatch_preserve_previous_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=fixture(tmp);d=dataset(Path(tmp)/'r.mpc');out=Path(tmp)/'output'
            def images(d,staging,**kw):p=staging/'chart.png';p.write_bytes(b'chart');return [p]
            with patch('mpc_echograms.plotting.export_images',images):
                m=export(d,out,[500],50,project_path=base.with_suffix('.frd'))
                self.assertTrue((out/'reflection_faces.csv').exists());self.assertEqual(m['native_project']['face_count'],1)
                saved=(out/'summary.json').read_bytes();vb=base.with_suffix('.fvt');b=bytearray(vb.read_bytes())
                for i in range(1,6):struct.pack_into('<f',b,30+i*40+20,2.)
                vb.write_bytes(b)
                with self.assertRaisesRegex(MPCError,'differ'):export(d,out,[500],50,project_path=base.with_suffix('.frd'),project_strict=True)
                self.assertEqual(saved,(out/'summary.json').read_bytes())
                export(d,out,[500],50);self.assertFalse((out/'project_room.json').exists())

    @unittest.skipUnless(importlib.util.find_spec('plotly'),'Optional Plotly not installed')
    def test_room_viewer_embeds_faces_and_only_explicit_coefficients(self):
        from mpc_echograms.viewer import export_viewer
        with tempfile.TemporaryDirectory() as tmp:
            p=read_project(fixture(tmp).with_suffix('.frd'));d=dataset(Path(tmp)/'r.mpc')
            name,=export_viewer(d,Path(tmp),[500,1000],project=p,audit=audit_project(p,d))
            text=name.read_text();self.assertIn('"material_front":"Test wall"',text);self.assertIn('coefficients unavailable',text)
            self.assertIn('Translucent room surfaces',text);self.assertIn('ray-pick',text);self.assertNotIn('<script src="https://',text)
