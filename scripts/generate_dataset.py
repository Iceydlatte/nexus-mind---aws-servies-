from pathlib import Path
import numpy as np
import pandas as pd
out = Path("data/generated/activities.csv")
out.parent.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(2026)
n = 1500
study = rng.integers(0, 480, n)
entertain = rng.integers(0, 600, n)
youtube = np.minimum(entertain, rng.integers(0, 300, n))
screen = np.minimum(1440, study + entertain + rng.integers(30, 300, n))
focus = np.minimum(12, study // 35 + rng.integers(0, 4, n))
planned = rng.integers(1, 9, n)
completion = np.clip(.15 + study / 700 - entertain / 1100 + rng.normal(0, .18, n), 0, 1)
completed = np.minimum(planned, np.floor(planned * completion).astype(int))
sleep = np.clip(rng.normal(7, 1.3, n), 3, 10)
switches = np.clip((entertain / 80 + rng.normal(2, 2, n)).astype(int), 0, 20)
score = study / 4 + focus * 8 + completed * 10 + sleep * 3 - entertain / 5 - switches * 2
level = np.where(score < 40, "LOW", np.where(score < 100, "MODERATE", "HIGH"))
df = pd.DataFrame({"study_minutes":study,"entertainment_minutes":entertain,"youtube_minutes":youtube,"screen_time_minutes":screen,"focus_sessions":focus,"tasks_completed":completed,"tasks_planned":planned,"sleep_duration":sleep.round(1),"context_switches":switches,"productivity_level":level})
df.to_csv(out, index=False)
print(f"Wrote {n} Development/Synthetic Dataset rows to {out}")
