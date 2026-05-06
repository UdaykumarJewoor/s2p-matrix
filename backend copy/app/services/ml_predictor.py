import os
import joblib
import pandas as pd
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

MODEL_DIR = os.path.join(os.path.dirname(__file__), '..', 'ml_models')
MODEL_PATH = os.path.join(MODEL_DIR, 'supplier_risk_rf.pkl')

_model = None

def load_model():
    """Lazy load the ML model into memory"""
    global _model
    if _model is None:
        if os.path.exists(MODEL_PATH):
            _model = joblib.load(MODEL_PATH)
            logger.info("Successfully loaded ML Supplier Risk RandomForest model.")
        else:
            logger.warning("ML model not found. Run scripts/train_ml_model.py first.")
    return _model

def predict_supplier_risk(features: Dict[str, Any]) -> Dict[str, Any]:
    """
    Predicts the probability of successful fulfillment (1.0 = 100% confidence)
    Expected features dict:
    {
        "hist_delivery_score": 0-100,
        "hist_quality_score": 0-100,
        "price_variance_pct": float (negative if cheap, positive if expensive),
        "is_oem": 1 or 0,
        "proposed_lead_time": int (days)
    }
    """
    model = load_model()
    
    if not model:
        # Fallback if model fails to load (return median neutral 50%)
        return {
            "success_probability": 0.50,
            "prediction_class": 0,
            "error": "Model not loaded"
        }

    # Format exactly as the training features expected
    # The order MUST mirror the training: 
    # ['hist_delivery_score', 'hist_quality_score', 'price_variance_pct', 'is_oem', 'proposed_lead_time']
    
    # Use pandas to guarantee order and shape
    df = pd.DataFrame([{
        'hist_delivery_score': features.get('hist_delivery_score', 75),
        'hist_quality_score': features.get('hist_quality_score', 75),
        'price_variance_pct': features.get('price_variance_pct', 0),
        'is_oem': features.get('is_oem', 0),
        'proposed_lead_time': features.get('proposed_lead_time', 15)
    }])

    # Probabilities returned as [P(class=0), P(class=1)]
    probs = model.predict_proba(df)[0]
    success_prob = float(probs[1])
    class_pred = int(model.predict(df)[0])

    return {
        "success_probability": success_prob,
        "prediction_class": class_pred, # 1=Success, 0=Risky
        "confidence_pct": round(success_prob * 100, 1)
    }
