"""Idempotent demo seed: users, alert rules, optional synthetic climate + ML."""
from __future__ import annotations

import argparse
import logging

from weatherpredict import auth, db, ml, notifications
from weatherpredict.batch.synthetic import generate_synthetic_dataset

logger = logging.getLogger("weatherpredict.seed")

DEMO_ADMIN = ("admin", "AdminPass123!")
DEMO_ANALYST = ("analyst", "AnalystPass123!")


def seed_users() -> None:
    db.ensure_indexes()
    if auth.get_user(DEMO_ADMIN[0]) is None:
        auth.create_user(
            DEMO_ADMIN[0],
            DEMO_ADMIN[1],
            role=auth.ADMINISTRATOR,
            email="admin@earthscape.local",
        )
        logger.info("Created demo Administrator")
    else:
        auth.set_password(DEMO_ADMIN[0], DEMO_ADMIN[1])
    if auth.get_user(DEMO_ANALYST[0]) is None:
        auth.create_user(
            DEMO_ANALYST[0],
            DEMO_ANALYST[1],
            role=auth.ANALYST,
            email="analyst@earthscape.local",
            region_focus="pacific_nw",
        )
        logger.info("Created demo Analyst")
    else:
        auth.set_password(DEMO_ANALYST[0], DEMO_ANALYST[1])
        auth.set_region_focus(DEMO_ANALYST[0], "pacific_nw", acting_user=auth.get_user(DEMO_ADMIN[0]))
    notifications.seed_default_rules()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed WeatherPredict demo accounts and optional data.")
    parser.add_argument("--with-data", action="store_true")
    parser.add_argument("--years", type=int, default=2)
    parser.add_argument("--train", action="store_true")
    args = parser.parse_args(argv)
    seed_users()
    admin = auth.get_user(DEMO_ADMIN[0])
    if args.with_data:
        generate_synthetic_dataset(years=args.years, user=admin, clear_existing=True)
    if args.train:
        ml.train_all(user=admin)
    print("Seed complete. Demo logins: admin / AdminPass123!  ·  analyst / AnalystPass123!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
