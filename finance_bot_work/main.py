from telegram.ext import Application
from config import TELEGRAM_TOKEN
from handlers import register_handlers
from scheduler import setup_scheduler
from database import init_db
import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

async def main():
    # Инициализация БД
    await init_db()
    
    # Создание приложения
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    register_handlers(application)
    
    # Настройка планировщика
    scheduler = await setup_scheduler(application)
    scheduler.start()
    
    # Специальный запуск для Windows
    try:
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        
        while True:
            await asyncio.sleep(3600)  # Бесконечный цикл с паузой
            
    except (asyncio.CancelledError, KeyboardInterrupt):
        await shutdown(application, scheduler)

async def shutdown(application, scheduler):
    """Корректное завершение работы"""
    logging.info("Завершение работы...")
    if scheduler.running:
        scheduler.shutdown(wait=False)
    await application.updater.stop()
    await application.stop()
    await application.shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Приложение остановлено пользователем")