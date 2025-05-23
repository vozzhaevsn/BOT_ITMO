import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update, Message, User as TgUser
from telegram.ext import ContextTypes
from handlers import track
from database import User, AsyncSessionLocal
import exchanges
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
    return context

# Добавление нового тикера

@pytest.mark.asyncio
@patch("handlers.exchanges.get_price", new_callable=AsyncMock)
async def test_add_tracked_ticker(mock_get_price, mock_update, mock_context):
    """Успешное добавление тикера с порогом 5%."""
    mock_context.args = ["BTCUSDT", "5"]
    mock_get_price.return_value = 50000.0
    
    with patch("handlers.AsyncSessionLocal", new_callable=AsyncMock) as mock_session:
        mock_session.return_value.__aenter__.return_value = mock_session
        mock_user = User(is_authenticated=True, tracked_tickers=[])
        mock_session.execute.return_value = MagicMock(scalar=MagicMock(return_value=mock_user))
        
        await track(mock_update, mock_context)
        
        # Проверка:
        # 1. Тикер добавлен в список
        assert len(mock_user.tracked_tickers) == 1
        assert mock_user.tracked_tickers[0]["ticker"] == "BTCUSDT"
        assert mock_user.tracked_tickers[0]["threshold"] == 5.0
        
        # 2. Бот отправляет подтверждение
        mock_update.message.reply_text.assert_awaited_with(
            "✅ Начинаю отслеживать BTCUSDT\n• Текущая цена: 50000.00\n• Порог уведомлений: 5.0%"
        )

# Обновление порога для существующего тикера
@pytest.mark.asyncio
@patch("handlers.exchanges.get_price", new_callable=AsyncMock)
async def test_update_ticker_threshold(mock_get_price, mock_update, mock_context):
    """Обновление порога с 5% до 10%."""
    mock_context.args = ["BTCUSDT", "10"]
    mock_get_price.return_value = 50000.0
    
    with patch("handlers.AsyncSessionLocal", new_callable=AsyncMock) as mock_session:
        mock_session.return_value.__aenter__.return_value = mock_session
        mock_user = User(
            is_authenticated=True,
            tracked_tickers=[{"ticker": "BTCUSDT", "threshold": 5.0}]
        )
        mock_session.execute.return_value = MagicMock(scalar=MagicMock(return_value=mock_user))
        
        await track(mock_update, mock_context)
        assert mock_user.tracked_tickers[0]["threshold"] == 10.0

# Удаление тикера из отслеживания

@pytest.mark.asyncio
async def test_remove_tracked_ticker(mock_update, mock_context):
    """Удаление тикера командой /track BTCUSDT remove."""
    mock_context.args = ["BTCUSDT", "remove"]
    
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

# Обновление времени отслеживания

@pytest.mark.asyncio
@patch("handlers.exchanges.get_price", new_callable=AsyncMock)
async def test_ticker_timestamp_update(mock_get_price, mock_update, mock_context):
    """Проверка обновления поля updated_at при изменении цены."""
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
        assert "updated_at" in mock_user.tracked_tickers[0]
        assert mock_user.tracked_tickers[0]["updated_at"] != "2023-01-01T00:00:00"

# Ошибка при получении цены

@pytest.mark.asyncio
@patch("handlers.exchanges.get_price", new_callable=AsyncMock)
async def test_track_price_error(mock_get_price, mock_update, mock_context):
    """Обработка ошибки API при получении цены."""
    mock_get_price.side_effect = Exception("API Error")
    mock_context.args = ["INVALID"]
    
    await track(mock_update, mock_context)
    mock_update.message.reply_text.assert_awaited_with(
        "⚠️ Не удалось получить текущую цену. Проверьте тикер."
    )