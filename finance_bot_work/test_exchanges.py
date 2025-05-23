import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from exchanges import (
    get_binance_price,
    get_bybit_price,
    get_moex_price,
    get_tinkoff_price,
    get_price
)
from binance import BinanceAPIException
from pybit.exceptions import InvalidRequestError
from tinkoff.invest import AsyncClient, InstrumentStatus, OrderBookResponse
from tinkoff.invest.schemas import Share
import aiohttp
import json

# Тесты для get_binance_price

@pytest.mark.asyncio
@patch("exchanges.BinanceClient.create", new_callable=AsyncMock)
async def test_get_binance_price_success(mock_client):
    """Успешный запрос цены BTCUSDT с Binance."""
    mock_instance = mock_client.return_value
    mock_instance.get_symbol_ticker.return_value = {"price": "50000.00"}
    
    price = await get_binance_price("BTCUSDT")
    assert price == 50000.0
    mock_instance.close_connection.assert_awaited_once()

@pytest.mark.asyncio
@patch("exchanges.BinanceClient.create", new_callable=AsyncMock)
async def test_get_binance_price_invalid_symbol(mock_client):
    """Ошибка при неверном тикере."""
    mock_instance = mock_client.return_value
    mock_instance.get_symbol_ticker.side_effect = BinanceAPIException("Invalid symbol")
    
    price = await get_binance_price("INVALID")
    assert price == 0.0

# Тесты для get_bybit_price

@patch("exchanges.BybitClient")
def test_get_bybit_price_success(mock_bybit):
    """Успешный запрос цены ETHUSDT с Bybit."""
    mock_instance = mock_bybit.return_value
    mock_instance.get_tickers.return_value = {
        "result": {"list": [{"symbol": "ETHUSDT", "lastPrice": "3000.00"}]}
    }
    
    price = get_bybit_price("ETHUSDT")
    assert price == 3000.0

@patch("exchanges.BybitClient")
def test_get_bybit_price_api_error(mock_bybit):
    """Ошибка API Bybit."""
    mock_instance = mock_bybit.return_value
    mock_instance.get_tickers.side_effect = InvalidRequestError("API Error")
    
    price = get_bybit_price("ETHUSDT")
    assert price == 0.0

# Тесты для get_moex_price

@pytest.mark.asyncio
@patch("aiohttp.ClientSession.get")
async def test_get_moex_price_success(mock_get):
    """Успешный запрос цены SBER с MOEX."""
    mock_response = AsyncMock()
    mock_response.json.return_value = {
        "marketdata": {"data": [[None] * 12 + [250.0]]}
    }
    mock_get.return_value.__aenter__.return_value = mock_response
    
    price = await get_moex_price("SBER")
    assert price == 250.0

@pytest.mark.asyncio
@patch("aiohttp.ClientSession.get")
async def test_get_moex_price_timeout(mock_get):
    """Таймаут при запросе к MOEX."""
    mock_get.side_effect = aiohttp.ClientError("Timeout")
    
    price = await get_moex_price("SBER")
    assert price == 0.0

# Тесты для get_tinkoff_price

@pytest.mark.asyncio
@patch("exchanges.TinkoffClient", new_callable=AsyncMock)
async def test_get_tinkoff_price_success(mock_tinkoff):
    """Успешный запрос цены GAZP через Tinkoff."""
    mock_client = mock_tinkoff.return_value.__aenter__.return_value
    mock_client.instruments.shares.return_value = [Share(ticker="GAZP", figi="FIGI_GAZP")]
    mock_client.market_data.get_order_book.return_value = OrderBookResponse(last_price=MagicMock(units=300))
    
    price = await get_tinkoff_price("GAZP")
    assert price == 300.0

@pytest.mark.asyncio
@patch("exchanges.TinkoffClient", new_callable=AsyncMock)
async def test_get_tinkoff_price_no_instrument(mock_tinkoff):
    """Тикер не найден в Tinkoff."""
    mock_client = mock_tinkoff.return_value.__aenter__.return_value
    mock_client.instruments.shares.return_value = []
    
    price = await get_tinkoff_price("UNKNOWN")
    assert price == 0.0

# Тесты для универсальной функции get_price

@pytest.mark.asyncio
@patch("exchanges.get_binance_price", new_callable=AsyncMock)
async def test_get_price_crypto(mock_binance):
    """Вызов Binance для криптовалюты."""
    mock_binance.return_value = 50000.0
    price = await get_price("BTCUSDT")
    mock_binance.assert_awaited_once_with("BTCUSDT")
    assert price == 50000.0

@pytest.mark.asyncio
@patch("exchanges.get_tinkoff_price", new_callable=AsyncMock)
@patch("exchanges.get_moex_price", new_callable=AsyncMock)
async def test_get_price_stocks(mock_moex, mock_tinkoff):
    """Вызов Tinkoff и MOEX для акций."""
    mock_tinkoff.return_value = 0.0  # Тикер не найден в Tinkoff
    mock_moex.return_value = 250.0
    
    price = await get_price("SBER")
    mock_tinkoff.assert_awaited_once_with("SBER")
    mock_moex.assert_awaited_once_with("SBER")
    assert price == 250.0

@pytest.mark.asyncio
@patch("exchanges.get_tinkoff_price", new_callable=AsyncMock)
async def test_get_price_tinkoff_fallback(mock_tinkoff):
    """Приоритет Tinkoff перед MOEX."""
    mock_tinkoff.return_value = 300.0
    price = await get_price("SBER")
    assert price == 300.0

@pytest.mark.asyncio
@patch("exchanges.get_tinkoff_price", new_callable=AsyncMock)
@patch("exchanges.get_moex_price", new_callable=AsyncMock)
async def test_get_price_all_failed(mock_moex, mock_tinkoff):
    """Все биржи вернули ошибку."""
    mock_tinkoff.return_value = 0.0
    mock_moex.return_value = 0.0
    
    price = await get_price("UNKNOWN")
    assert price == 0.0