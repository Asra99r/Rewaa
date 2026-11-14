"""Run: python -m unittest discover -s tests -v"""
import base64
import os
import tempfile
import unittest
from pathlib import Path

_TEMP = tempfile.TemporaryDirectory()
os.environ['RAWAA_DB'] = str(Path(_TEMP.name) / 'test.sqlite3')
from fastapi.testclient import TestClient
from app import app

class RawaaWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg=TestClient(app)
        cls.op=TestClient(app)
        assert cls.reg.post('/api/login',json={'email':'regulator@rawaa.local','password':'Rawaa2026!'}).status_code==200
        assert cls.op.post('/api/login',json={'email':'operator@rawaa.local','password':'Rawaa2026!'}).status_code==200

    def test_demo_role_switch_and_production_guard(self):
        client = TestClient(app)
        self.assertEqual(client.post('/api/login', json={'email':'operator@rawaa.local','password':'Rawaa2026!'}).status_code, 200)
        r = client.post('/api/demo/switch-role', json={'role':'regulator'})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(client.get('/api/me').json()['role'], 'regulator')
        self.assertEqual(client.post('/api/demo/switch-role', json={'role':'unknown'}).status_code, 400)
        old = os.environ.get('RAWAA_ENV')
        try:
            os.environ['RAWAA_ENV'] = 'production'
            self.assertEqual(client.post('/api/demo/switch-role', json={'role':'operator'}).status_code, 403)
            self.assertFalse(client.get('/api/dashboard').json()['role_switch_enabled'])
        finally:
            if old is None: os.environ.pop('RAWAA_ENV', None)
            else: os.environ['RAWAA_ENV'] = old

    def test_auth_and_roles(self):
        self.assertEqual(TestClient(app).get('/api/areas').status_code,401)
        self.assertEqual(self.reg.get('/api/me').json()['role'],'regulator')
        self.assertEqual(self.op.get('/api/me').json()['role'],'operator')
        self.assertEqual(self.op.post('/api/areas',json={'name_ar':'اختبار','name_en':'Test','geometry':{'type':'Polygon','coordinates':[[[39.17,21.53],[39.18,21.53],[39.18,21.54],[39.17,21.53]]]}}).status_code,403)

    def test_dashboard_is_labeled_demo(self):
        r=self.reg.get('/api/dashboard')
        self.assertEqual(r.status_code,200)
        d=r.json()
        self.assertTrue(d['demo'])
        self.assertGreaterEqual(d['counts']['total'],5)
        self.assertTrue(all(a['metrics']['source'].startswith('DEMO') for a in d['areas'][:5]))

    def test_area_create_and_csv_import(self):
        g={'type':'Polygon','coordinates':[[[39.21,21.52],[39.215,21.52],[39.215,21.526],[39.21,21.52]]]}
        r=self.reg.post('/api/areas',json={'name_ar':'حديقة اختبار','name_en':'Test area','geometry':g,'assigned_operator':2})
        self.assertEqual(r.status_code,201,r.text)
        aid=r.json()['id']
        self.assertEqual(self.reg.get(f'/api/areas/{aid}').json()['metrics']['status'],'insufficient')
        self.assertEqual(self.op.get(f'/api/areas/{aid}').status_code,200)
        csv_text='date,ndvi,ndmi,valid_pixels_pct\n2026-01-01,0.60,0.21,95\n2026-02-01,0.60,0.21,95\n2026-03-01,0.45,0.20,95\n2026-04-01,0.42,0.19,95\n'
        r=self.reg.post(f'/api/areas/{aid}/import-csv',json={'csv_text':csv_text})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['imported'],4)
        m=self.reg.get(f'/api/areas/{aid}').json()['metrics']
        self.assertEqual(m['status'],'high')
        self.assertFalse(m['demo'])
        r=self.reg.post(f'/api/areas/{aid}/scan')
        self.assertEqual(r.status_code,200,r.text)
        alert_id=r.json()['alert_id']
        self.assertEqual(self.reg.post(f'/api/areas/{aid}/scan').status_code,409)
        r=self.reg.post(f'/api/alerts/{alert_id}/assign',json={'priority':'high'})
        self.assertEqual(r.status_code,200,r.text)
        taskid=r.json()['id']
        self.assertIn(taskid,[x['id'] for x in self.op.get('/api/tasks').json()])
        self.assertEqual(self.op.patch(f'/api/tasks/{taskid}',json={'status':'in_progress'}).status_code,200)
        self.assertEqual(self.op.patch(f'/api/tasks/{taskid}',json={'status':'pending_review'}).status_code,400)
        self.assertEqual(self.op.patch(f'/api/tasks/{taskid}',json={'status':'pending_review','actual_cause':'Broken irrigation','action':'Fixed pipe'}).status_code,200)
        self.assertEqual(self.reg.patch(f'/api/tasks/{taskid}',json={'status':'closed'}).status_code,200)
        self.assertEqual(self.op.patch(f'/api/tasks/{taskid}',json={'status':'in_progress'}).status_code,409)
        self.assertEqual(self.op.get('/api/activity').status_code,403)

    def test_photo_evidence_is_access_controlled(self):
        task_id=next(x['id'] for x in self.op.get('/api/tasks').json() if x['status']!='closed')
        png='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO9WkHkAAAAASUVORK5CYII='
        data='data:image/png;base64,'+png
        r=self.op.post(f'/api/tasks/{task_id}/photo',json={'kind':'before','data_url':data})
        self.assertEqual(r.status_code,200,r.text)
        self.assertIn('image/png',self.reg.get(f'/api/tasks/{task_id}/photo/before').headers.get('content-type',''))
        self.assertEqual(TestClient(app).get(f'/api/tasks/{task_id}/photo/before').status_code,401)
        self.assertEqual(self.reg.post(f'/api/tasks/{task_id}/photo',json={'kind':'after','data_url':data}).status_code,403)

    def test_satellite_credentials_missing_is_explicit(self):
        result=self.reg.get('/api/integrations').json()
        self.assertFalse(result['copernicus_configured'])
        self.assertEqual(self.reg.post('/api/areas/1/sync-satellite',json={}).status_code,422)

    def test_imagery_validation_and_missing_credentials(self):
        self.assertEqual(self.reg.post('/api/areas/1/imagery',json={'month':'2026-01','layer':'ndvi'}).status_code,422)
        self.assertEqual(self.reg.post('/api/areas/1/imagery',json={'month':'0000-01','layer':'ndvi'}).status_code,400)
        self.assertEqual(self.reg.post('/api/areas/1/imagery',json={'month':'2026-13','layer':'ndvi'}).status_code,422)
        self.assertEqual(TestClient(app).post('/api/areas/1/imagery',json={'month':'2026-01','layer':'ndvi'}).status_code,401)

    def test_report(self):
        r=self.reg.get('/api/reports/tasks.csv')
        self.assertEqual(r.status_code,200)
        self.assertIn('text/csv',r.headers['content-type'])

if __name__=='__main__':
    unittest.main()
