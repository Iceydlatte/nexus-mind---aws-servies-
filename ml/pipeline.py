from pathlib import Path
import os
import pandas as pd
import mlflow
import mlflow.sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, confusion_matrix
from sklearn.model_selection import train_test_split
from ml.features import FEATURES, FEATURE_NAMES, engineer, validate_activity

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "generated" / "activities.csv"

def train():
    df = pd.read_csv(DATA)
    required = set(FEATURES + ["productivity_level"])
    if not required.issubset(df.columns):
        raise ValueError(f"Missing columns: {sorted(required - set(df.columns))}")
    if df.duplicated().any() or df[list(required)].isna().any().any():
        raise ValueError("Training data has duplicate rows or missing required values")
    for row in df[FEATURES].to_dict(orient="records"):
        validate_activity(row)
    X = [engineer(row) for row in df[FEATURES].to_dict(orient="records")]
    y = df["productivity_level"]
    x_train, x_test, y_train, y_test = train_test_split(X, y, test_size=.2, random_state=42, stratify=y)
    model = RandomForestClassifier(n_estimators=160, min_samples_leaf=2, class_weight="balanced", random_state=42)
    # SQLite supports MLflow's model registry locally; artifacts remain on local disk.
    tracking = os.getenv("MLFLOW_TRACKING_URI", "sqlite:///./mlflow.db")
    mlflow.set_tracking_uri(tracking)
    mlflow.set_experiment("nexus-mind-productivity")
    with mlflow.start_run() as run:
        model.fit(x_train, y_train)
        pred = model.predict(x_test)
        metrics = {"accuracy": accuracy_score(y_test, pred), "precision_macro": precision_score(y_test, pred, average="macro", zero_division=0), "recall_macro": recall_score(y_test, pred, average="macro", zero_division=0), "f1_macro": f1_score(y_test, pred, average="macro", zero_division=0)}
        mlflow.log_params({"model": "RandomForestClassifier", "n_estimators": 160, "test_size": .2, "feature_version": "1.0"})
        mlflow.log_metrics(metrics)
        mlflow.sklearn.log_model(model, "model", registered_model_name="productivity_model")
        mlflow.log_dict({"confusion_matrix": confusion_matrix(y_test, pred, labels=["LOW", "MODERATE", "HIGH"]).tolist(), "labels": ["LOW", "MODERATE", "HIGH"], "feature_names": FEATURE_NAMES}, "evaluation.json")
        threshold = float(os.getenv("MIN_MACRO_F1", ".60"))
        accepted = metrics["f1_macro"] >= threshold
        metadata = {"name": "productivity", "version": run.info.run_id[:8], "run_id": run.info.run_id, "metrics": metrics, "trained_at": pd.Timestamp.utcnow().isoformat(), "dataset": "Development/Synthetic Dataset", "feature_version": "1.0", "framework": "scikit-learn", "status": "PRODUCTION" if accepted else "REJECTED"}
        if accepted:
            from pathlib import Path
            import joblib, json
            artifact_dir=ROOT/"artifacts"; artifact_dir.mkdir(exist_ok=True)
            joblib.dump({"model":model,"metadata":metadata},artifact_dir/f"productivity_v{metadata['version']}.joblib")
            joblib.dump({"model":model,"metadata":metadata},artifact_dir/"productivity_production.joblib")
            (artifact_dir/f"productivity_v{metadata['version']}.json").write_text(json.dumps(metadata,indent=2))
        return metadata
