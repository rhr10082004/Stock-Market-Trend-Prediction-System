import os
import unittest
from unittest.mock import patch
from uuid import uuid4

os.environ.setdefault("APP_MODE", "demo")
os.environ.setdefault("JWT_SECRET", "test-only-stockai-secret-with-32-bytes-or-more")

from backend.app import app


class StockAIAPITests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()
        self.email = f"{uuid4().hex}@example.test"
        self.password = "correct-horse-battery"

    def register_and_login(self):
        registered = self.client.post("/api/auth/register", json={
            "name": "Test User", "email": self.email, "password": self.password,
        })
        self.assertEqual(registered.status_code, 200)
        logged_in = self.client.post("/api/auth/login", json={
            "email": self.email, "password": self.password,
        })
        self.assertEqual(logged_in.status_code, 200)
        return {"Authorization": f"Bearer {logged_in.json['token']}"}

    def test_health_stock_list_and_validation(self):
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        stocks = self.client.get("/api/stocks").json["stocks"]
        self.assertIn("RELIANCE", stocks)
        self.assertEqual(len(stocks), 8)
        self.assertEqual(self.client.get("/api/history/INVALID").status_code, 400)

    def test_authentication_validation_and_protected_history(self):
        self.assertEqual(self.client.get("/api/predictions").status_code, 401)
        self.assertEqual(self.client.post("/api/auth/register", json={
            "name": "A", "email": "invalid", "password": "short",
        }).status_code, 400)
        headers = self.register_and_login()
        duplicate = self.client.post("/api/auth/register", json={
            "name": "Test User", "email": self.email, "password": self.password,
        })
        self.assertEqual(duplicate.status_code, 409)
        wrong = self.client.post("/api/auth/login", json={
            "email": self.email, "password": "incorrect-password",
        })
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(self.client.get("/api/predictions", headers=headers).status_code, 200)
        self.assertEqual(self.client.post("/api/auth/logout", headers=headers).status_code, 200)

    @patch("yfinance.download", side_effect=ConnectionError("offline"))
    def test_demo_data_indicators_prediction_metrics_and_history(self, _download):
        history = self.client.get("/api/history/RELIANCE?range=6mo")
        self.assertEqual(history.status_code, 200)
        self.assertIn("DEMO DATA MODE", history.json["mode"])
        self.assertEqual(len(history.json["data"]), 130)
        self.assertEqual(self.client.get("/api/indicators/RELIANCE").status_code, 200)

        headers = self.register_and_login()
        prediction = self.client.post("/api/predict", json={"symbol": "RELIANCE"}, headers=headers)
        self.assertEqual(prediction.status_code, 200, prediction.json)
        result = prediction.json
        self.assertIn(result["trend"], {"UP", "DOWN", "SIDEWAYS"})
        self.assertIn(result["model"], {"Logistic Regression", "Random Forest", "BASELINE DEMO MODEL"})
        metrics = result["metrics"][result["model"]]
        self.assertTrue({"accuracy", "precision", "recall", "f1", "confusion_matrix"}.issubset(metrics))
        self.assertEqual(len(metrics["confusion_matrix"]), 3)
        performance = self.client.get("/api/model-performance?symbol=RELIANCE", headers=headers)
        self.assertEqual(performance.status_code, 200)
        self.assertTrue(performance.json["metrics"])
        self.assertEqual(len(self.client.get("/api/predictions", headers=headers).json["predictions"]), 1)


if __name__ == "__main__":
    unittest.main()
