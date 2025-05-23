import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from database import User, NewsSubscription, Base, init_db
import bcrypt
from datetime import datetime

# Тесты на создание таблиц и структуру БД

@pytest.mark.asyncio
async def test_table_creation(async_session):
    """Тест 1: Проверка создания таблиц users и news_subscriptions."""
    # Проверка через системные таблицы SQLite
    result = await async_session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table'")
    )
    tables = [row[0] for row in result.fetchall()]
    assert "users" in tables
    assert "news_subscriptions" in tables

# Тесты для модели User

@pytest.mark.asyncio
async def test_user_creation(async_session):
    """Тест 2: Создание пользователя с валидными данными."""
    user = User(
        email="user@test.com",
        password_hash=bcrypt.hashpw(b"password", bcrypt.gensalt()).decode(),
        telegram_id=12345,
        is_authenticated=True,
        subscriptions={"crypto": True}
    )
    async_session.add(user)
    await async_session.commit()

    # Проверка записи
    db_user = await async_session.get(User, user.id)
    assert db_user.email == "user@test.com"
    assert db_user.telegram_id == 12345
    assert db_user.subscriptions == {"crypto": True}

@pytest.mark.asyncio
async def test_unique_email_constraint(async_session):
    """Тест 3: Проверка уникальности email."""
    user1 = User(email="duplicate@test.com", password_hash="hash1")
    async_session.add(user1)
    await async_session.commit()

    user2 = User(email="duplicate@test.com", password_hash="hash2")
    async_session.add(user2)
    with pytest.raises(IntegrityError):
        await async_session.commit()

@pytest.mark.asyncio
async def test_password_hashing_in_db(async_session):
    """Тест 4: Проверка хеширования пароля при сохранении."""
    raw_password = "s3cr3t"
    user = User(
        email="user@test.com",
        password_hash=bcrypt.hashpw(raw_password.encode(), bcrypt.gensalt()).decode()
    )
    async_session.add(user)
    await async_session.commit()

    db_user = await async_session.get(User, user.id)
    assert bcrypt.checkpw(raw_password.encode(), db_user.password_hash.encode())

@pytest.mark.asyncio
async def test_json_fields_defaults(async_session):
    """Тест 5: Проверка дефолтных значений JSON-полей."""
    user = User(email="user@test.com")
    async_session.add(user)
    await async_session.commit()

    assert user.subscriptions == {"crypto": False, "stocks": False, "news": False}
    assert user.tracked_tickers == []

# Тесты для модели NewsSubscription

@pytest.mark.asyncio
async def test_news_subscription_creation(async_session):
    """Тест 6: Создание подписки на новости."""
    user = User(email="user@test.com")
    async_session.add(user)
    await async_session.commit()

    sub = NewsSubscription(user_id=user.id, query="Bitcoin")
    async_session.add(sub)
    await async_session.commit()

    db_sub = await async_session.get(NewsSubscription, sub.id)
    assert db_sub.query == "Bitcoin"
    assert db_sub.user_id == user.id

@pytest.mark.asyncio
async def test_cascade_delete_subscriptions(async_session):
    """Тест 7: Каскадное удаление подписок при удалении пользователя."""
    user = User(email="user@test.com")
    sub = NewsSubscription(user_id=user.id, query="AI")
    async_session.add_all([user, sub])
    await async_session.commit()

    await async_session.delete(user)
    await async_session.commit()

    # Проверка, что подписка удалена
    result = await async_session.execute(select(NewsSubscription))
    assert len(result.scalars().all()) == 0

# Тесты на обновление данных

@pytest.mark.asyncio
async def test_update_user_subscriptions(async_session):
    """Тест 8: Обновление подписок пользователя."""
    user = User(email="user@test.com", subscriptions={"crypto": False})
    async_session.add(user)
    await async_session.commit()

    # Обновление подписок
    user.subscriptions = {"crypto": True, "news": True}
    await async_session.commit()

    db_user = await async_session.get(User, user.id)
    assert db_user.subscriptions == {"crypto": True, "news": True}

@pytest.mark.asyncio
async def test_tracked_tickers_update(async_session):
    """Тест 9: Добавление и обновление отслеживаемых тикеров."""
    user = User(email="user@test.com")
    async_session.add(user)
    await async_session.commit()

    # Добавляем тикер
    user.tracked_tickers = [{
        "ticker": "BTCUSDT",
        "threshold": 5.0,
        "added_at": datetime.now().isoformat()
    }]
    await async_session.commit()

    # Обновляем порог
    user.tracked_tickers[0]["threshold"] = 10.0
    await async_session.commit()

    db_user = await async_session.get(User, user.id)
    assert db_user.tracked_tickers[0]["threshold"] == 10.0

# Тесты на граничные случаи

@pytest.mark.asyncio
async def test_empty_email(async_session):
    """Тест 10: Попытка создания пользователя без email."""
    user = User(password_hash="hash")
    async_session.add(user)
    with pytest.raises(IntegrityError):
        await async_session.commit()

@pytest.mark.asyncio
async def test_invalid_json(async_session):
    """Тест 11: Некорректные данные в JSON-полях."""
    user = User(email="user@test.com", subscriptions="invalid_data")
    async_session.add(user)
    with pytest.raises(IntegrityError):
        await async_session.commit()