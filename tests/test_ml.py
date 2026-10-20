import pandas as pd
import pytest
from ml.features import engineer, validate_activity

def row():
    return dict(study_minutes=120, entertainment_minutes=90, youtube_minutes=30, screen_time_minutes=300, focus_sessions=3, tasks_completed=2, tasks_planned=4, sleep_duration=7, context_switches=5)

def test_shared_features_are_finite_and_stable():
    x=engineer(row())
    assert len(x)==13
    assert x[-2]==.5
    assert all(pd.notna(v) for v in x)

def test_invalid_activity_rejected():
    bad=row(); bad["sleep_duration"]=-1
    with pytest.raises(ValueError): validate_activity(bad)

def test_task_count_validation():
    bad=row(); bad["tasks_completed"]=5
    with pytest.raises(ValueError): validate_activity(bad)
