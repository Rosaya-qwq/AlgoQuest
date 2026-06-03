import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter
from nonebot.log import logger


nonebot.init()

driver = nonebot.get_driver()
driver.register_adapter(OneBotV11Adapter)


@driver.on_startup
async def ensure_problem_buffers() -> None:
    from bot.services.problem_random import ensure_all_difficulties_on_startup
    from bot.services.submission import remove_invalid_rank_users, repair_rank_stats

    try:
        removed_user_ids = remove_invalid_rank_users()
        if removed_user_ids:
            logger.info(f"Removed invalid rank user ids on startup: {removed_user_ids}")
        if repair_rank_stats():
            logger.info("Repaired aggregate rank counters from per-source solved counts")
        await ensure_all_difficulties_on_startup()
    except Exception:
        logger.exception("Unexpected failure while ensuring problem buffers")


@driver.on_bot_connect
async def cleanup_bot_rank_record(bot) -> None:
    from bot.services.submission import remove_rank_user

    try:
        if remove_rank_user(str(bot.self_id)):
            logger.info(f"Removed bot self_id {bot.self_id} from rank stats")
    except Exception:
        logger.exception("Unexpected failure while removing bot rank stats")


nonebot.load_from_toml("pyproject.toml")


if __name__ == "__main__":
    nonebot.run()
