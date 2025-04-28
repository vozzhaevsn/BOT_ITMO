import aiohttp
from pybit.unified_trading import HTTP as BybitClient
from binance import AsyncClient as BinanceClient
from tinkoff.invest import AsyncClient as TinkoffClient
from config import *

async def get_binance_price(symbol: str) -> float:
    try:
        client = await BinanceClient.create(BINANCE_API_KEY, BINANCE_SECRET)
        ticker = await client.get_symbol_ticker(symbol=symbol)
        return float(ticker['price']) if ticker else 0.0
    except Exception as e:
        print(f"Binance Error: {e}")
        return 0.0
    finally:
        await client.close_connection()

async def get_bybit_price(symbol: str) -> float:
    try:
        client = BybitClient(
            api_key=BYBIT_API_KEY,
            api_secret=BYBIT_SECRET,
            testnet=False
        )
        response = client.get_tickers(category="spot", symbol=symbol)
        return float(response['result']['list'][0]['lastPrice']) if response['result'] else 0.0
    except Exception as e:
        print(f"Bybit API Error: {e}")
        return 0.0

async def get_moex_price(ticker: str) -> float:
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://iss.moex.com/iss/engines/stock/markets/shares/securities/{ticker}.json"
            async with session.get(url) as response:
                data = await response.json()
                return float(data["marketdata"]["data"][0][12]) if data.get("marketdata") else 0.0
    except Exception as e:
        print(f"MOEX Error: {e}")
        return 0.0

async def get_tinkoff_price(ticker: str) -> float:
    try:
        async with TinkoffClient(TINKOFF_TOKEN) as client:
            instruments = (await client.instruments.shares()).instruments
            for instrument in instruments:
                if instrument.ticker == ticker.upper():
                    orderbook = await client.market_data.get_order_book(figi=instrument.figi, depth=1)
                    return float(orderbook.last_price.units)
            return 0.0
    except Exception as e:
        print(f"Tinkoff Error: {e}")
        return 0.0
    
async def get_price(ticker: str) -> float:
    """Универсальная функция для получения цены"""
    if any(ticker.endswith(ext) for ext in ("USDT", "BTC", "ETH")):
        return await get_binance_price(ticker)
    else:
        try:
            return await get_tinkoff_price(ticker)
        except Exception:
            return await get_moex_price(ticker)