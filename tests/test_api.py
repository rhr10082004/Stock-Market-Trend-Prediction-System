import os, unittest
from unittest.mock import patch
from uuid import uuid4
import pandas as pd

os.environ["JWT_SECRET"]="unit-test-secret-that-is-long-enough-123456"
os.environ["DATABASE_URL"]="sqlite:///test.db"
from backend.app import app
from backend import market

class APITests(unittest.TestCase):
    def setUp(self):
        os.environ["DATABASE_URL"]="sqlite:///test_api.db"
        app.config.update(TESTING=True); self.c=app.test_client(); self.email=uuid4().hex+"@example.test"

    def tearDown(self): pass

    def register(self):
        r=self.c.post('/api/auth/register',json={"name":"Research User","email":self.email,"password":"correct-horse-battery"})
        self.assertEqual(r.status_code,200,r.json)
        return {"Authorization":"Bearer "+r.json["token"]}

    def test_auth_hash_duplicate_wrong_password_and_protection(self):
        self.assertEqual(self.c.get('/api/predictions').status_code,401)
        self.assertEqual(self.c.post('/api/auth/register',json={"name":"x","email":"bad","password":"x"}).status_code,400)
        h=self.register()
        self.assertEqual(self.c.post('/api/auth/register',json={"name":"Research User","email":self.email,"password":"correct-horse-battery"}).status_code,409)
        self.assertEqual(self.c.post('/api/auth/login',json={"email":self.email,"password":"wrong-password"}).status_code,401)
        self.assertEqual(self.c.get('/api/predictions',headers=h).status_code,200)
        self.assertEqual(self.c.post('/api/auth/logout',headers=h).status_code,200)

    def test_real_data_api_shape_and_fail_closed(self):
        self.assertEqual(self.c.get('/api/stocks').json['stocks'][0]['symbol'],'NIFTY50')
        idx=pd.date_range('2025-01-01',periods=280,freq='B')
        values=[22000+i*2 for i in range(280)]
        frame=pd.DataFrame({"open":values,"high":[x+10 for x in values],"low":[x-10 for x in values],"close":values,"volume":[1000]*280},index=idx)
        with patch('backend.market.history',return_value=frame):
            # history is imported as a function in app; patch the provider-facing wrapper instead.
            pass
        with patch('backend.app.history_payload',return_value={"symbol":"NIFTY50","provider":"Yahoo Finance","interval":"1d","as_of":"2026-01-01","data":[{"date":"2026-01-01","close":23000}]}):
            response=self.c.get('/api/history/NIFTY50')
            self.assertEqual(response.status_code,200); self.assertEqual(response.json['provider'],'Yahoo Finance')
        self.assertEqual(self.c.get('/api/history/RELIANCE').status_code,400)
        with patch('backend.app.history_payload',side_effect=market.MarketDataUnavailable('provider unavailable')):
            self.assertEqual(self.c.get('/api/history/NIFTY50').status_code,503)

    def test_vercel_requires_persistent_database(self):
        os.environ['VERCEL']='1'
        try:
            response=self.c.get('/api/health')
            self.assertEqual(response.status_code,503)
            self.assertEqual(response.json['database'],'unavailable')
        finally:
            os.environ.pop('VERCEL',None)

    def test_saved_forecast_scoped_to_user(self):
        h=self.register()
        frame=pd.DataFrame({"close":[20000]},index=pd.to_datetime(['2026-01-01']))
        result={"symbol":"NIFTY50","forecast_return":.002,"forecast_close":20040,"model":"test estimator","as_of":"2026-01-01","metrics":{},"dm_tests":[],"diagnostics":{},"backtest":{},"test_period":{},"feature_importance":[]}
        with patch('backend.app.history',return_value=frame),patch('backend.app.train_and_predict',return_value=result):
            response=self.c.post('/api/predict',json={"symbol":"NIFTY50"},headers=h)
        self.assertEqual(response.status_code,200,response.json)
        rows=self.c.get('/api/predictions',headers=h).json['predictions']
        self.assertEqual(len(rows),1); self.assertEqual(rows[0]['trend'],'UP')
        self.assertEqual(self.c.post('/api/predict',json={"symbol":"RELIANCE"},headers=h).status_code,400)

if __name__=='__main__': unittest.main()
