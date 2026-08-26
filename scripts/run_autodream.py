from config.settings import get_settings
from db.session import build_session_factory, init_db, make_engine
from services.autodream import AutoDreamService


def main(user_id: str, force: bool = False) -> None:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    init_db(engine)
    db = build_session_factory(engine)()
    try:
        print(AutoDreamService(db, settings).run(user_id, force))
        db.commit()
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("user_id")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    main(args.user_id, args.force)

