import asyncio
import logging
import sys

from pydantic import ValidationError

from spark.config import get_settings
from spark.core.admin import AdminService
from spark.core.photos import FaceEngine, ModelsMissingError
from spark.core.profiles import ProfileService
from spark.db.base import init_db, make_engine, make_sessionmaker

log = logging.getLogger("spark")


async def main() -> None:
    settings = get_settings()
    if not settings.telegram_bot_token and not settings.discord_bot_token:
        sys.exit("Set TELEGRAM_BOT_TOKEN and/or DISCORD_BOT_TOKEN in .env")
    if not settings.owner_tg_ids and not settings.owner_dc_ids:
        log.warning("No OWNER_TG_IDS / OWNER_DC_IDS set: nobody has admin access!")

    engine = make_engine(settings.database_url)
    await init_db(engine)
    face = FaceEngine(settings)
    profiles = ProfileService(make_sessionmaker(engine), settings, face)
    admin = AdminService(settings, profiles)

    tasks = []
    if settings.telegram_bot_token:
        from spark.adapters.telegram.bot import run_telegram

        tasks.append(run_telegram(settings, profiles, admin))
    if settings.discord_bot_token:
        from spark.adapters.discord.bot import run_discord

        tasks.append(run_discord(settings, profiles, admin))
    try:
        await asyncio.gather(*tasks)
    finally:
        await engine.dispose()


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    try:
        asyncio.run(main())
    except ValidationError as exc:
        sys.exit(f"Config error in .env:\n{exc}\n\nTip: run `python scripts/init_env.py` to create .env")
    except ModelsMissingError as exc:
        sys.exit(str(exc))
    except KeyboardInterrupt:
        log.info("stopped")


if __name__ == "__main__":
    run()
