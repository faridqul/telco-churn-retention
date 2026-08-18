import joblib
import pandas as pd

from config import MODEL_PATH, load_threshold, validate_feature_schema
from feature_engineering_telco import engineer_features

INPUT_PATH = "simulated_new_customers.csv"
OUTPUT_PATH = "retention_campaign_targets.csv"


def main():
    validate_feature_schema()  # fail fast on feature/model schema drift
    threshold = load_threshold()
    print(f"Using threshold: {threshold}")

    print("Loading model...")
    model = joblib.load(MODEL_PATH)

    print("Loading new customer data...")
    new_customers = pd.read_csv(INPUT_PATH)

    print("Engineering features...")
    new_customers = engineer_features(new_customers)

    print("Generating predictions...")
    probabilities = model.predict_proba(new_customers)[:, 1]
    predictions = (probabilities >= threshold).astype(int)

    new_customers["Churn_Probability"] = probabilities
    new_customers["Target_For_Retention"] = predictions
    new_customers.to_csv(OUTPUT_PATH, index=False)

    print(f"Success! {predictions.sum()} of {len(predictions)} customers flagged for retention.")


if __name__ == "__main__":
    main()
