from sqlalchemy import select
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from database import AsyncSessionLocal, User, NewsSubscription
import bcrypt
import exchanges
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Аутентификация
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    await update.message.reply_text(
        "📈 Финансовый бот готов к работе!\n"
        "Используйте /help для списка команд\n"
        "Для доступа ко всем функциям:\n"
        "/register - регистрация\n"
        "/login - вход"
    )

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Регистрация нового пользователя"""
    if len(context.args) != 2:
        await update.message.reply_text("Формат: /register email пароль")
        return
    
    email, password = context.args[0], context.args[1]
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    
    async with AsyncSessionLocal() as session:
        # Проверка существующего пользователя
        existing_user = await session.execute(
            select(User).where(User.email == email)
        )
        if existing_user.scalar():
            await update.message.reply_text("❌ Пользователь уже существует")
            return
        
        # Создание нового пользователя
        new_user = User(
            email=email,
            password_hash=hashed,
            telegram_id=update.effective_user.id,
            is_authenticated=True
        )
        session.add(new_user)
        await session.commit()
    
    await update.message.reply_text(
        "✅ Регистрация успешна! Вы автоматически вошли в систему.\n"
        "Используйте /help для списка команд"
    )

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вход в систему"""
    if len(context.args) != 2:
        await update.message.reply_text("Формат: /login email пароль")
        return
    
    email, password = context.args[0], context.args[1]
    
    async with AsyncSessionLocal() as session:
        user = await session.execute(
            select(User).where(User.email == email)
        )
        user = user.scalar()
        
        if not user or not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
            await update.message.reply_text("❌ Неверный email или пароль")
            return
        
        user.is_authenticated = True
        user.telegram_id = update.effective_user.id  # Обновляем telegram_id
        await session.commit()
    
    await update.message.reply_text("🔓 Вы успешно вошли в систему!")

async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выход из системы"""
    async with AsyncSessionLocal() as session:
        user = await session.execute(
            select(User).where(User.telegram_id == update.effective_user.id)
        )
        user = user.scalar()
        
        if user:
            user.is_authenticated = False
            await session.commit()
    
    await update.message.reply_text("🔒 Вы вышли из системы")

# Финансовые команды
async def stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение текущей цены актива"""
    if not context.args:
        await update.message.reply_text(
            "Примеры использования:\n"
            "/stock BTCUSDT - криптовалюта (Binance/Bybit)\n"
            "/stock SBER - акции (MOEX/Тинькофф)\n"
            "/stock AAPL - акции (Тинькофф)"
        )
        return
    
    ticker = context.args[0].upper()
    message = f"📊 *{ticker}*\n"
    
    try:
        if any(ticker.endswith(ext) for ext in ("USDT", "BTC", "ETH")):
            binance_price = await exchanges.get_binance_price(ticker)
            bybit_price = await exchanges.get_bybit_price(ticker)
            message += (
                f"• Binance: ${binance_price:.2f}\n"
                f"• Bybit: ${bybit_price:.2f}"
            )
        else:
            moex_price = await exchanges.get_moex_price(ticker)
            tinkoff_price = await exchanges.get_tinkoff_price(ticker)
            message += (
                f"• Тинькофф: {tinkoff_price:.2f} RUB\n"
                f"• MOEX: {moex_price:.2f} RUB"
            )
        
        await update.message.reply_text(message, parse_mode="Markdown")
    
    except Exception as e:
        logging.error(f"Ошибка в команде /stock: {e}")
        await update.message.reply_text("⚠️ Ошибка при получении данных. Попробуйте позже.")

# Подписки и уведомления
async def set_subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Настройка подписок через инлайн-клавиатуру"""
    keyboard = [
        [InlineKeyboardButton("Криптовалюта", callback_data='crypto')],
        [InlineKeyboardButton("Акции", callback_data='stocks')],
        [InlineKeyboardButton("Новости", callback_data='news')]
    ]
    await update.message.reply_text(
        "🔔 Выберите категории для ежедневной сводки:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавление тикера для отслеживания"""
    try:
        if len(context.args) < 1:
            await update.message.reply_text(
                "Формат: /track <тикер> [порог_в_%]\n"
                "Пример: /track BTCUSDT 5 - уведомлять при изменении цены на 5%"
            )
            return

        ticker = context.args[0].upper()
        threshold = float(context.args[1]) if len(context.args) > 1 else 5.0

        async with AsyncSessionLocal() as session:
            # Проверка авторизации
            user = await session.execute(
                select(User).where(User.telegram_id == update.effective_user.id)
            )
            user = user.scalar()
            
            if not user or not user.is_authenticated:
                await update.message.reply_text("❌ Для использования этой команды войдите в систему: /login")
                return

            # Получение текущей цены
            try:
                current_price = await exchanges.get_price(ticker)
            except Exception as e:
                logging.error(f"Ошибка получения цены для {ticker}: {e}")
                await update.message.reply_text("⚠️ Не удалось получить текущую цену. Проверьте тикер.")
                return

            # Обновление списка отслеживаемых тикеров
            tickers = user.tracked_tickers.copy()
            existing_index = next(
                (i for i, t in enumerate(tickers) if t["ticker"] == ticker),
                None
            )

            if existing_index is not None:
                tickers[existing_index] = {
                    "ticker": ticker,
                    "threshold": threshold,
                    "last_price": current_price,
                    "updated_at": datetime.now().isoformat()
                }
            else:
                tickers.append({
                    "ticker": ticker,
                    "threshold": threshold,
                    "last_price": current_price,
                    "added_at": datetime.now().isoformat()
                })

            user.tracked_tickers = tickers
            await session.commit()

        await update.message.reply_text(
            f"✅ Начинаю отслеживать {ticker}\n"
            f"• Текущая цена: {current_price:.2f}\n"
            f"• Порог уведомлений: {threshold}%"
        )

    except Exception as e:
        logging.error(f"Ошибка в команде /track: {e}")
        await update.message.reply_text("⚠️ Произошла ошибка. Попробуйте позже.")

async def news_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подписка на новости"""
    if not context.args:
        await update.message.reply_text(
            "Формат: /news_subscribe <запрос>\n"
            "Пример: /news_subscribe Bitcoin"
        )
        return
    
    query = " ".join(context.args)
    
    async with AsyncSessionLocal() as session:
        user = await session.execute(
            select(User).where(User.telegram_id == update.effective_user.id)
        )
        user = user.scalar()
        
        if not user:
            await update.message.reply_text("❌ Сначала войдите в систему (/login)")
            return
        
        # Проверка существующей подписки
        existing = await session.execute(
            select(NewsSubscription)
            .where(NewsSubscription.user_id == user.id)
            .where(NewsSubscription.query.ilike(query))
        )
        
        if existing.scalar():
            await update.message.reply_text(f"ℹ️ Вы уже подписаны на новости по запросу: '{query}'")
            return
        
        # Добавление новой подписки
        new_sub = NewsSubscription(
            user_id=user.id,
            query=query
        )
        session.add(new_sub)
        await session.commit()
    
    await update.message.reply_text(
        f"📰 Вы подписались на новости по запросу: '{query}'"
    )

# Справочная информация
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список всех доступных команд"""
    commands = [
        ("/start", "Начало работы"),
        ("/help", "Справка по командам"),
        ("/register <email> <пароль>", "Регистрация"),
        ("/login <email> <пароль>", "Вход в систему"),
        ("/logout", "Выход из системы"),
        ("/stock <тикер>", "Котировки актива"),
        ("/subscriptions", "Настройка подписок"),
        ("/track <тикер> [порог%]", "Отслеживание цен"),
        ("/news_subscribe <запрос>", "Подписка на новости")
    ]
    
    text = "📋 Доступные команды:\n\n" + "\n".join(
        f"• {cmd} — {desc}" for cmd, desc in commands
    )
    
    await update.message.reply_text(text)

# Обработчик инлайн-кнопок
async def subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора категорий подписок"""
    query = update.callback_query
    await query.answer()
    
    category = query.data
    user_id = query.from_user.id
    
    async with AsyncSessionLocal() as session:
        user = await session.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = user.scalar()
        
        if user:
            subscriptions = user.subscriptions.copy()
            subscriptions[category] = not subscriptions.get(category, False)
            user.subscriptions = subscriptions
            await session.commit()
            
            status = "включены" if subscriptions[category] else "отключены"
            await query.edit_message_text(
                f"Подписка на '{category}' {status}.\n"
                f"Текущие настройки: {subscriptions}"
            )

# Регистрация обработчиков
def register_handlers(application):
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("register", register))
    application.add_handler(CommandHandler("login", login))
    application.add_handler(CommandHandler("logout", logout))
    application.add_handler(CommandHandler("stock", stock))
    application.add_handler(CommandHandler("subscriptions", set_subscriptions))
    application.add_handler(CommandHandler("track", track))
    application.add_handler(CommandHandler("news_subscribe", news_subscribe))
    application.add_handler(CallbackQueryHandler(subscription_callback, pattern='^(crypto|stocks|news)$'))