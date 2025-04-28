from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from database import AsyncSessionLocal, User
import exchanges
import logging

logger = logging.getLogger(__name__)

async def setup_scheduler(application):
    scheduler = AsyncIOScheduler(
        timezone="Europe/Moscow",
        job_defaults={"misfire_grace_time": 60*5}  # Разрешить выполнение с задержкой до 5 минут
    )

    async def send_daily_summary():
        """Ежедневная сводка для пользователей с подписками"""
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(User).where(User.subscriptions != {})
                )
                users = result.scalars().all()

                for user in users:
                    summary = []
                    try:
                        if user.subscriptions.get("crypto"):
                            btc_price = await exchanges.get_binance_price("BTCUSDT")
                            summary.append(f"₿ Bitcoin: ${btc_price:.2f}")
                    except Exception as e:
                        logger.error(f"Ошибка получения цены BTC: {e}")

                    try:
                        if user.subscriptions.get("stocks"):
                            sber_price = await exchanges.get_moex_price("SBER")
                            summary.append(f"🏦 Сбербанк: {sber_price:.2f} RUB")
                    except Exception as e:
                        logger.error(f"Ошибка получения цены SBER: {e}")

                    if summary:
                        await application.bot.send_message(
                            chat_id=user.telegram_id,
                            text="📰 Ежедневная сводка:\n" + "\n".join(summary)
                        )

        except Exception as e:
            logger.error(f"Ошибка в send_daily_summary: {e}", exc_info=True)

    async def check_price_alerts():
        """Проверка пороговых значений цен"""
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(User).where(User.tracked_tickers != [])
                )
                users = result.scalars().all()

                for user in users:
                    alerts = []
                    for item in user.tracked_tickers:
                        ticker = item.get("ticker")
                        threshold = item.get("threshold", 5)
                        
                        if not ticker:
                            continue

                        try:
                            current_price = await exchanges.get_price(ticker)
                            last_price = item.get("last_price")

                            if last_price is None:
                                item["last_price"] = current_price
                                continue

                            change = abs((current_price - last_price) / last_price * 100)
                            if change >= threshold:
                                alerts.append(
                                    f"🚨 {ticker}: {change:.2f}% "
                                    f"({last_price:.2f} → {current_price:.2f})"
                                )
                            item["last_price"] = current_price

                        except Exception as e:
                            logger.error(f"Ошибка обработки {ticker}: {e}")

                    if alerts:
                        await application.bot.send_message(
                            chat_id=user.telegram_id,
                            text="🔔 Активированы пороговые значения:\n" + "\n".join(alerts)
                        )

                    await session.commit()

        except Exception as e:
            logger.error(f"Ошибка в check_price_alerts: {e}", exc_info=True)

    # Настройка расписания
    scheduler.add_job(
        send_daily_summary,
        CronTrigger(
            hour=9,
            minute=0,
            timezone="Europe/Moscow"
        ),
        name="daily_summary"
    )

    scheduler.add_job(
        check_price_alerts,
        "interval",
        minutes=5,
        name="price_alerts"
    )

    return scheduler