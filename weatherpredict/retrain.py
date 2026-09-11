"""Retrain all ML models. ``python -m weatherpredict.retrain``."""
from __future__ import annotations

from weatherpredict import auth, ml
from weatherpredict.seed import DEMO_ADMIN, seed_users


def main() -> int:
    seed_users()
    admin = auth.get_user(DEMO_ADMIN[0])
    run = ml.train_all(user=admin)
    print(f"Retrain {run.get('status')} stats={run.get('stats')}")
    return 0 if run.get("status") == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
