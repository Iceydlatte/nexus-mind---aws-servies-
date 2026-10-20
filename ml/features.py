"""Shared local feature validation and engineering for offline model training."""
import numpy as np

FEATURES = ["study_minutes", "entertainment_minutes", "youtube_minutes", "screen_time_minutes", "focus_sessions", "tasks_completed", "tasks_planned", "sleep_duration", "context_switches"]

def validate_activity(data: dict) -> dict:
    values = {k: data[k] for k in FEATURES}
    for key, value in values.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value):
            raise ValueError(f"{key} must be a finite number")
        if value < 0:
            raise ValueError(f"{key} cannot be negative")
    if values["tasks_completed"] > values["tasks_planned"]:
        raise ValueError("tasks_completed cannot exceed tasks_planned")
    if values["sleep_duration"] > 24 or values["screen_time_minutes"] > 1440:
        raise ValueError("sleep_duration must be at most 24 hours and screen time at most 1440 minutes")
    return values

def engineer(row: dict) -> list[float]:
    study, entertainment, screen, planned = row["study_minutes"], row["entertainment_minutes"], row["screen_time_minutes"], row["tasks_planned"]
    return [row[k] for k in FEATURES] + [study/max(screen,1), entertainment/max(screen,1), row["tasks_completed"]/max(planned,1), row["focus_sessions"]/max(study/60,1/60)]

FEATURE_NAMES = FEATURES + ["study_ratio", "entertainment_ratio", "task_completion_rate", "focus_per_study_hour"]
