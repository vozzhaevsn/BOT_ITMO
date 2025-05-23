import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import InlineKeyboardMarkup, Update, Message, User as TgUser, CallbackQuery
from telegram.ext import ContextTypes
from handlers import (
    start, register, login, logout, stock, set_subscriptions,
    track, news_subscribe, help_command, subscription_callback
)
from database import User, NewsSubscription, AsyncSessionLocal
import bcrypt
from datetime import datetime
import logging

# Фикстуры для моков Telegram API
@pytest.fixture
def mock_update():
    update = AsyncMock(spec=Update)
    update.message = AsyncMock(spec=Message)
    update.message.reply_text = AsyncMock()
    update.effective_user = AsyncMock(spec=TgUser)
    update.effective_user.id = 12345
    return update

@pytest.fixture
def mock_context():
    context = AsyncMock(spec=ContextTypes.DEFAULT_TYPE)
    context.args = []
    context.bot = AsyncMock()
    return context

# Тест 1: Команда /start
@pytest.mark.asyncio
async def test_start(mock_update, mock_context):
    await start(mock_update, mock_context)
    mock_update.message.reply_text.assert_awaited_with(
        "📈 Финансовый бот готов к работе!\n"
        "Используйте /help для списка команд\n"
        "Для доступа ко всем функциям:\n"
        "/register - регистрация\n"
        "/login - вход"
    )

# Тест 2: Успешная регистрация
@pytest.mark.asyncio
async def test_register_success(mock_update, mock_context):
    mock_context.args = ["test@example.com", "password123"]
    
    with patch("handlers.AsyncSessionLocal", new_callable=AsyncMock) as mock_session:
        mock_session.return_value.__aenter__.return_value = mock_session
        mock_session.execute.return_value = MagicMock(scalar=MagicMock(return_value=None))
        
        await register(mock_update, mock_context)
        
        # Проверка создания пользователя
        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()
        mock_update.message.reply_text.assert_awaited_with(
            "✅ Регистрация успешна! Вы автоматически вошли в систему.\n"
            "Используйте /help для списка команд"
        )

# Тест 3: Регистрация с существующим email
@pytest.mark.asyncio
async def test_register_duplicate_email(mock_update, mock_context):
    mock_context.args = ["duplicate@test.com", "password123"]
    
    with patch("handlers.AsyncSessionLocal", new_callable=AsyncMock) as mock_session:
        mock_session.return_value.__aenter__.return_value = mock_session
        mock_session.execute.return_value = MagicMock(scalar=MagicMock(return_value=User()))  # Пользователь уже существует
        
        await register(mock_update, mock_context)
        mock_update.message.reply_text.assert_awaited_with("❌ Пользователь уже существует")

# Тест 4: Успешный вход
@pytest.mark.asyncio
async def test_login_success(mock_update, mock_context):
    mock_context.args = ["test@example.com", "password123"]
    hashed_pw = bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode()
    
    with patch("handlers.AsyncSessionLocal", new_callable=AsyncMock) as mock_session:
        mock_session.return_value.__aenter__.return_value = mock_session
        mock_user = User(email="test@example.com", password_hash=hashed_pw)
        mock_session.execute.return_value = MagicMock(scalar=MagicMock(return_value=mock_user))
        
        await login(mock_update, mock_context)
        mock_session.commit.assert_awaited_once()
        mock_update.message.reply_text.assert_awaited_with("🔓 Вы успешно вошли в систему!")

# Тест 5: Неверный пароль
@pytest.mark.asyncio
async def test_login_wrong_password(mock_update, mock_context):
    mock_context.args = ["test@example.com", "wrongpass"]
    hashed_pw = bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode()
    
    with patch("handlers.AsyncSessionLocal", new_callable=AsyncMock) as mock_session:
        mock_session.return_value.__aenter__.return_value = mock_session
        mock_user = User(email="test@example.com", password_hash=hashed_pw)
        mock_session.execute.return_value = MagicMock(scalar=MagicMock(return_value=mock_user))
        
        await login(mock_update, mock_context)
        mock_update.message.reply_text.assert_awaited_with("❌ Неверный email или пароль")

# Тест 6: Выход из системы
@pytest.mark.asyncio
async def test_logout(mock_update, mock_context):
    with patch("handlers.AsyncSessionLocal", new_callable=AsyncMock) as mock_session:
        mock_session.return_value.__aenter__.return_value = mock_session
        mock_user = User(is_authenticated=True)
        mock_session.execute.return_value = MagicMock(scalar=MagicMock(return_value=mock_user))
        
        await logout(mock_update, mock_context)
        assert mock_user.is_authenticated is False
        mock_session.commit.assert_awaited_once()
        mock_update.message.reply_text.assert_awaited_with("🔒 Вы вышли из системы")

# Тест 7: Запрос котировок для криптовалюты
@pytest.mark.asyncio
@patch("handlers.exchanges.get_binance_price", new_callable=AsyncMock)
@patch("handlers.exchanges.get_bybit_price", new_callable=MagicMock)
async def test_stock_crypto(mock_bybit, mock_binance, mock_update, mock_context):
    mock_binance.return_value = 50000.0
    mock_bybit.return_value = 49000.0
    mock_context.args = ["BTCUSDT"]
    
    await stock(mock_update, mock_context)
    mock_update.message.reply_text.assert_awaited_with(
        "📊 *BTCUSDT*\n• Binance: $50000.00\n• Bybit: $49000.00",
        parse_mode="Markdown"
    )

# Тест 8: Запрос котировок для акций
@pytest.mark.asyncio
@patch("handlers.exchanges.get_moex_price", new_callable=AsyncMock)
@patch("handlers.exchanges.get_tinkoff_price", new_callable=AsyncMock)
async def test_stock_stocks(mock_tinkoff, mock_moex, mock_update, mock_context):
    mock_tinkoff.return_value = 300.0
    mock_moex.return_value = 280.0
    mock_context.args = ["SBER"]
    
    await stock(mock_update, mock_context)
    mock_update.message.reply_text.assert_awaited_with(
        "📊 *SBER*\n• Тинькофф: 300.00 RUB\n• MOEX: 280.00 RUB",
        parse_mode="Markdown"
    )

# Тест 9: Ошибка при запросе котировок
@pytest.mark.asyncio
@patch("handlers.exchanges.get_price", new_callable=AsyncMock)
async def test_stock_error(mock_get_price, mock_update, mock_context):
    mock_get_price.return_value = 0.0
    mock_context.args = ["INVALID"]
    
    await stock(mock_update, mock_context)
    mock_update.message.reply_text.assert_awaited_with("⚠️ Ошибка при получении данных. Попробуйте позже.")

# Тест 10: Настройка подписок через инлайн-кнопки
@pytest.mark.asyncio
async def test_set_subscriptions(mock_update, mock_context):
    await set_subscriptions(mock_update, mock_context)
    mock_update.message.reply_text.assert_awaited_with(
        "🔔 Выберите категории для ежедневной сводки:",
        reply_markup=MagicMock(spec=InlineKeyboardMarkup)
    )

# Тест 11: Добавление тикера через /track
@pytest.mark.asyncio
@patch("handlers.exchanges.get_price", new_callable=AsyncMock)
async def test_track_ticker(mock_get_price, mock_update, mock_context):
    mock_context.args = ["BTCUSDT", "5"]
    mock_get_price.return_value = 50000.0
    
    with patch("handlers.AsyncSessionLocal", new_callable=AsyncMock) as mock_session:
        mock_session.return_value.__aenter__.return_value = mock_session
        mock_user = User(is_authenticated=True, tracked_tickers=[])
        mock_session.execute.return_value = MagicMock(scalar=MagicMock(return_value=mock_user))
        
        await track(mock_update, mock_context)
        assert len(mock_user.tracked_tickers) == 1
        mock_session.commit.assert_awaited_once()
        mock_update.message.reply_text.assert_awaited_with(
            "✅ Начинаю отслеживать BTCUSDT\n• Текущая цена: 50000.00\n• Порог уведомлений: 5.0%"
        )

# Тест 12: Подписка на новости
@pytest.mark.asyncio
async def test_news_subscribe(mock_update, mock_context):
    mock_context.args = ["Bitcoin"]
    
    with patch("handlers.AsyncSessionLocal", new_callable=AsyncMock) as mock_session:
        mock_session.return_value.__aenter__.return_value = mock_session
        mock_user = User(is_authenticated=True)
        mock_session.execute.return_value = MagicMock(scalar=MagicMock(return_value=mock_user))
        
        await news_subscribe(mock_update, mock_context)
        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()
        mock_update.message.reply_text.assert_awaited_with("📰 Вы подписались на новости по запросу: 'Bitcoin'")

# Тест 13: Команда /help
@pytest.mark.asyncio
async def test_help_command(mock_update, mock_context):
    await help_command(mock_update, mock_context)
    mock_update.message.reply_text.assert_awaited_once()

# Тест 14: Обработка инлайн-кнопок
@pytest.mark.asyncio
async def test_subscription_callback(mock_update):
    query = AsyncMock(spec=CallbackQuery)
    query.data = "crypto"
    query.from_user.id = 12345
    update = AsyncMock(spec=Update)
    update.callback_query = query
    
    with patch("handlers.AsyncSessionLocal", new_callable=AsyncMock) as mock_session:
        mock_session.return_value.__aenter__.return_value = mock_session
        mock_user = User(subscriptions={"crypto": False})
        mock_session.execute.return_value = MagicMock(scalar=MagicMock(return_value=mock_user))
        
        await subscription_callback(update, None)
        assert mock_user.subscriptions["crypto"] is True
        query.edit_message_text.assert_awaited_with(
            "Подписка на 'crypto' включены.\nТекущие настройки: {'crypto': True}"
        )
#Тест 15: Обновление времени updated_at в отслеживаемых тикерах
@pytest.mark.asyncio
@patch("handlers.exchanges.get_price", new_callable=AsyncMock)
async def test_tracked_tickers_timestamp_update(mock_get_price, mock_update, mock_context):
    mock_context.args = ["BTCUSDT"]
    mock_get_price.return_value = 50000.0
    
    with patch("handlers.AsyncSessionLocal", new_callable=AsyncMock) as mock_session:
        mock_session.return_value.__aenter__.return_value = mock_session
        mock_user = User(
            is_authenticated=True,
            tracked_tickers=[{
                "ticker": "BTCUSDT",
                "threshold": 5.0,
                "added_at": "2023-01-01T00:00:00"
            }]
        )
        mock_session.execute.return_value = MagicMock(scalar=MagicMock(return_value=mock_user))
        
        await track(mock_update, mock_context)
        # Проверяем, что `updated_at` обновлен
        assert "updated_at" in mock_user.tracked_tickers[0]
        assert mock_user.tracked_tickers[0]["updated_at"] != "2023-01-01T00:00:00"

#Тест 16: Удаление тикера из отслеживания
@pytest.mark.asyncio
async def test_remove_tracked_ticker(mock_update, mock_context):
    mock_context.args = ["BTCUSDT", "remove"]  # Пример команды: /track BTCUSDT remove
    
    with patch("handlers.AsyncSessionLocal", new_callable=AsyncMock) as mock_session:
        mock_session.return_value.__aenter__.return_value = mock_session
        mock_user = User(
            is_authenticated=True,
            tracked_tickers=[{"ticker": "BTCUSDT", "threshold": 5.0}]
        )
        mock_session.execute.return_value = MagicMock(scalar=MagicMock(return_value=mock_user))
        
        await track(mock_update, mock_context)
        assert len(mock_user.tracked_tickers) == 0
        mock_update.message.reply_text.assert_awaited_with("🗑️ Тикер BTCUSDT удален из отслеживания.")

#Тест 17: Уведомление при достижении порога
@pytest.mark.asyncio
@patch("handlers.exchanges.get_price", new_callable=AsyncMock)
async def test_price_alert_notification(mock_get_price, mock_update, mock_context):
    mock_get_price.return_value = 55000.0  # +10% от 50000 (порог 5%)
    mock_context.args = ["BTCUSDT"]
    
    with patch("handlers.AsyncSessionLocal", new_callable=AsyncMock) as mock_session:
        mock_session.return_value.__aenter__.return_value = mock_session
        mock_user = User(
            is_authenticated=True,
            tracked_tickers=[{
                "ticker": "BTCUSDT",
                "threshold": 5.0,
                "last_price": 50000.0
            }]
        )
        mock_session.execute.return_value = MagicMock(scalar=MagicMock(return_value=mock_user))
        
        await track(mock_update, mock_context)
        # Проверка отправки уведомления
        mock_context.bot.send_message.assert_awaited_with(
            chat_id=mock_user.telegram_id,
            text="🔔 Активированы пороговые значения:\n🚨 BTCUSDT: 10.00% (50000.00 → 55000.00)"
        )

#Тест 18: Обработка ошибки при обновлении цены

@pytest.mark.asyncio
@patch("handlers.exchanges.get_price", new_callable=AsyncMock)
async def test_track_price_update_error(mock_get_price, mock_update, mock_context):
    mock_get_price.side_effect = Exception("Binance API Error")
    mock_context.args = ["BTCUSDT"]
    
    with patch("handlers.AsyncSessionLocal", new_callable=AsyncMock) as mock_session:
        mock_session.return_value.__aenter__.return_value = mock_session
        mock_user = User(is_authenticated=True)
        mock_session.execute.return_value = MagicMock(scalar=MagicMock(return_value=mock_user))
        
        await track(mock_update, mock_context)
        mock_update.message.reply_text.assert_awaited_with(
            "⚠️ Произошла ошибка. Попробуйте позже."
        )

#Тест 19: Проверка формата команды /help

@pytest.mark.asyncio
async def test_help_command_format(mock_update, mock_context):
    await help_command(mock_update, mock_context)
    # Проверяем, что ответ содержит список команд
    reply_text = mock_update.message.reply_text.call_args[0][0]
    assert "/register" in reply_text
    assert "/track" in reply_text
    assert "Примеры использования" not in reply_text  # Формат должен быть кратким

#Тест 20: Попытка подписки на новости без запроса

@pytest.mark.asyncio
async def test_news_subscribe_empty_query(mock_update, mock_context):
    mock_context.args = []  # Пользователь не указал запрос
    
    await news_subscribe(mock_update, mock_context)
    mock_update.message.reply_text.assert_awaited_with(
        "Формат: /news_subscribe <запрос>\nПример: /news_subscribe Bitcoin"
    )