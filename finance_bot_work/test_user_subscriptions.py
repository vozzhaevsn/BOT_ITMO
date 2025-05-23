import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from handlers import (
    set_subscriptions,
    subscription_callback,
    news_subscribe,
    send_daily_summary,
    check_price_alerts
)
from database import User, NewsSubscription, AsyncSessionLocal
import exchanges
from datetime import datetime
import logging

# Фикстуры для моков Telegram API
@pytest.fixture
def mock_update():
    update = AsyncMock(spec=Update)
    update.callback_query = AsyncMock(spec=CallbackQuery)
    update.callback_query.data = "crypto"
    update.callback_query.from_user.id = 12345
    update.callback_query.edit_message_text = AsyncMock()
    return update

@pytest.fixture
def mock_context():
    context = AsyncMock(spec=ContextTypes.DEFAULT_TYPE)
    context.bot = AsyncMock()
    return context

# Настройка подписок через инлайн-кнопки
@pytest.mark.asyncio
async def test_set_subscriptions(mock_update, mock_context):
    """Проверка отображения клавиатуры с категориями."""
    await set_subscriptions(mock_update, mock_context)
    
    # Проверяем, что отправлены кнопки
    mock_update.message.reply_text.assert_awaited_with(
        "🔔 Выберите категории для ежедневной сводки:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Криптовалюта", callback_data='crypto')],
            [InlineKeyboardButton("Акции", callback_data='stocks')],
            [InlineKeyboardButton("Новости", callback_data='news')]
        ])
    )

# Отправка ежедневной сводки
@pytest.mark.asyncio
@patch("exchanges.get_binance_price", new_callable=AsyncMock)
async def test_send_daily_summary(mock_binance, mock_context):
    """Проверка отправки сводки пользователю с подпиской на крипту."""
    mock_binance.return_value = 50000.0  # Цена BTC
    
    # Создаем пользователя с подпиской
    user = User(telegram_id=12345, subscriptions={"crypto": True})
    
    with patch("database.AsyncSessionLocal", new_callable=AsyncMock) as mock_session:
        mock_session.return_value.__aenter__.return_value = mock_session
        mock_session.execute.return_value = MagicMock(scalars=MagicMock(return_value=[user]))
        
        await send_daily_summary(mock_context)
        
        # Проверяем отправку сообщения
        mock_context.bot.send_message.assert_awaited_with(
            chat_id=12345,
            text="📰 Ежедневная сводка:\n₿ Bitcoin: $50000.00"
        )

# Подписка на новости по ключевому слову
@pytest.mark.asyncio
async def test_news_subscribe_success(mock_update, mock_context):
    """Успешная подписка на новости."""
    mock_context.args = ["Bitcoin"]
    
    with patch("database.AsyncSessionLocal", new_callable=AsyncMock) as mock_session:
        mock_session.return_value.__aenter__.return_value = mock_session
        mock_user = User(is_authenticated=True)
        mock_session.execute.return_value = MagicMock(scalar=MagicMock(return_value=mock_user))
        
        await news_subscribe(mock_update, mock_context)
        
        # Проверяем добавление подписки
        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()
        mock_update.message.reply_text.assert_awaited_with(
            "📰 Вы подписались на новости по запросу: 'Bitcoin'"
        )

# Попытка подписки без авторизации
@pytest.mark.asyncio
async def test_news_subscribe_unauthorized(mock_update, mock_context):
    """Попытка подписки без входа в систему."""
    mock_context.args = ["Bitcoin"]
    
    with patch("database.AsyncSessionLocal", new_callable=AsyncMock) as mock_session:
        mock_session.return_value.__aenter__.return_value = mock_session
        mock_session.execute.return_value = MagicMock(scalar=MagicMock(return_value=None))
        
        await news_subscribe(mock_update, mock_context)
        mock_update.message.reply_text.assert_awaited_with(
            "❌ Сначала войдите в систему (/login)"
        )

# Уведомление при достижении порога
@pytest.mark.asyncio
@patch("exchanges.get_price", new_callable=AsyncMock)
async def test_price_alert_notification(mock_get_price, mock_context):
    """Проверка отправки уведомления при изменении цены на 5%."""
    mock_get_price.return_value = 105.0  # Изменение на 5% (исходная цена 100)
    
    # Пользователь с отслеживаемым тикером
    user = User(
        telegram_id=12345,
        tracked_tickers=[{
            "ticker": "AAPL",
            "threshold": 5.0,
            "last_price": 100.0,
            "added_at": datetime.now().isoformat()
        }]
    )
    
    with patch("database.AsyncSessionLocal", new_callable=AsyncMock) as mock_session:
        mock_session.return_value.__aenter__.return_value = mock_session
        mock_session.execute.return_value = MagicMock(scalars=MagicMock(return_value=[user]))
        
        await check_price_alerts(mock_context)
        
        # Проверка уведомления
        mock_context.bot.send_message.assert_awaited_with(
            chat_id=12345,
            text="🔔 Активированы пороговые значения:\n🚨 AAPL: 5.00% (100.0 → 105.0)"
        )

# Отсутствие уведомления при малом изменении
@pytest.mark.asyncio
@patch("exchanges.get_price", new_callable=AsyncMock)
async def test_no_alert_below_threshold(mock_get_price, mock_context):
    """Изменение цены ниже порога (3% при пороге 5%)."""
    mock_get_price.return_value = 103.0
    
    user = User(
        telegram_id=12345,
        tracked_tickers=[{
            "ticker": "AAPL",
            "threshold": 5.0,
            "last_price": 100.0,
            "added_at": datetime.now().isoformat()
        }]
    )
    
    with patch("database.AsyncSessionLocal", new_callable=AsyncMock) as mock_session:
        mock_session.return_value.__aenter__.return_value = mock_session
        mock_session.execute.return_value = MagicMock(scalars=MagicMock(return_value=[user]))
        
        await check_price_alerts(mock_context)
        mock_context.bot.send_message.assert_not_called()

# Обработка ошибки в задаче отправки сводки
@pytest.mark.asyncio
@patch("exchanges.get_binance_price", new_callable=AsyncMock)
async def test_daily_summary_error(mock_binance, mock_context, caplog):
    """Проверка логирования ошибки при получении цены."""
    mock_binance.side_effect = Exception("Binance API Error")
    
    user = User(telegram_id=12345, subscriptions={"crypto": True})
    
    with patch("database.AsyncSessionLocal", new_callable=AsyncMock) as mock_session:
        mock_session.return_value.__aenter__.return_value = mock_session
        mock_session.execute.return_value = MagicMock(scalars=MagicMock(return_value=[user]))
        
        await send_daily_summary(mock_context)
        assert "Ошибка получения цены BTC" in caplog.text