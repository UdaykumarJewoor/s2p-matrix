import os
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
import joblib

# Ensure model directory exists
MODEL_DIR = os.path.join(os.path.dirname(__file__), '..', 'backend', 'app', 'ml_models')
os.makedirs(MODEL_DIR, exist_ok=True)
MODEL_PATH = os.path.join(MODEL_DIR, 'supplier_risk_rf.pkl')

def generate_synthetic_data(num_records=1500):
    """
    Generate synthetic historical procurement data.
    Features:
    - hist_delivery_score: 0-100 (Vendor's past on-time % score)
    - hist_quality_score: 0-100 (Vendor's past material acceptance % score)
    - price_variance_pct: % diff vs market benchmark (negative means cheaper)
    - is_oem: 1 if OEM, 0 if distributor
    - proposed_lead_time: days
    Target:
    - success: 1 (fulfilled safely), 0 (failed/delayed/rejected)
    """
    np.random.seed(42)  # For reproducibility

    data = {
        'hist_delivery_score': np.random.normal(75, 15, num_records).clip(0, 100),
        'hist_quality_score': np.random.normal(80, 12, num_records).clip(0, 100),
        'price_variance_pct': np.random.normal(0, 15, num_records), # e.g., -5 is 5% below budget
        'is_oem': np.random.choice([0, 1], num_records, p=[0.7, 0.3]),
        'proposed_lead_time': np.random.normal(14, 7, num_records).clip(1, 60).astype(int),
    }
    
    df = pd.DataFrame(data)

    # Function to determine synthetic "success" based on realistic procurement logic
    def determine_success(row):
        prob = 0.5
        
        # Higher past scores increase success probability
        if row['hist_delivery_score'] > 70: prob += 0.2
        if row['hist_delivery_score'] < 40: prob -= 0.3
        if row['hist_quality_score'] > 70: prob += 0.2
        if row['hist_quality_score'] < 40: prob -= 0.3
        
        # OEMs are generally safer for quality
        if row['is_oem'] == 1: prob += 0.1
        
        # Extremely cheap quotes (too good to be true) often fail/delay
        if row['price_variance_pct'] < -25: prob -= 0.2
        
        # Reward competitive pricing inside a safe margin
        if -10 <= row['price_variance_pct'] <= 5: prob += 0.2
        
        # High prices are very unfavorable / risky ROI
        if row['price_variance_pct'] > 15: prob -= 0.2
        if row['price_variance_pct'] > 30: prob -= 0.2
        
        # Short lead times from weak vendors fail
        if row['proposed_lead_time'] < 5 and row['hist_delivery_score'] < 70:
            prob -= 0.25
            
        # Reward realistically fast lead times
        if 5 <= row['proposed_lead_time'] <= 12: prob += 0.15
        
        # Long lead times are fundamentally risky for project execution
        if row['proposed_lead_time'] > 20: prob -= 0.15
        if row['proposed_lead_time'] > 30: prob -= 0.2

        # Clip probability
        prob = max(0, min(1, prob))
        
        # Random pick based on computed probability
        return np.random.binomial(1, prob)

    df['success'] = df.apply(determine_success, axis=1)
    return df

def train_model():
    print("1. Generating synthetic historical procurement data...")
    df = generate_synthetic_data()
    print(f"   Generated {len(df)} records. Success rate: {df['success'].mean():.1%}")

    X = df[['hist_delivery_score', 'hist_quality_score', 'price_variance_pct', 'is_oem', 'proposed_lead_time']]
    y = df['success']

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    print("\n2. Training Random Forest Classifier...")
    model = RandomForestClassifier(n_estimators=100, max_depth=6, random_state=42)
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    print(f"\n3. Evaluation Metrics:")
    print(f"   Accuracy: {acc:.2%}")
    print("\n   Detailed Report:")
    print(classification_report(y_test, y_pred))

    print(f"\n4. Saving ML model to {MODEL_PATH}")
    joblib.dump(model, MODEL_PATH)
    print("   Model saved successfully! Ready for real-time inference.")

if __name__ == "__main__":
    train_model()
