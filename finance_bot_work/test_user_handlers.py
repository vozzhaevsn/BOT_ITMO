import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update, Message, User as TgUser
from telegram.ext import ContextTypes
from handlers import register, login, logout
from database import User, AsyncSessionLocal
import bcrypt

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

# Регистрация нового пользователя
@pytest.mark.asyncio
async def test_register_new_user(mock_update, mock_context):
    """Проверка успешной регистрации."""
    mock_context.args = ["test@example.com", "password123"]
    
    with patch("handlers.AsyncSessionLocal", new_callable=AsyncMock) as mock_session:
        # Мок пустой БД (пользователь не существует)
        mock_session.return_value.__aenter__.return_value = mock_session
        mock_session.execute.return_value = MagicMock(scalar=MagicMock(return_value=None))
        
        await register(mock_update, mock_context)
        
        # Проверка:
        # 1. Пользователь добавлен в БД
        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()
        
        # 2. Пароль хешируется
        added_user = mock_session.add.call_args[0][0]
        assert bcrypt.checkpw(b"password123", added_user.password_hash.encode())
        
        # 3. Пользователь аутентифицирован
        assert added_user.is_authenticated is True
        
        # 4. Бот отправляет подтверждение
        mock_update.message.reply_text.assert_awaited_with(
            "✅ Регистрация успешна! Вы автоматически вошли в систему.\nИспользуйте /help для списка команд"
        )

# Попытка регистрации с существующим email

@pytest.mark.asyncio
async def test_register_duplicate_email(mock_update, mock_context):
    """Проверка обработки дублирующегося email."""
    mock_context.args = ["duplicate@test.com", "password123"]
    
    with patch("handlers.AsyncSessionLocal", new_callable=AsyncMock) as mock_session:
        # Мок существующего пользователя
        mock_session.return_value.__aenter__.return_value = mock_session
        mock_session.execute.return_value = MagicMock(scalar=MagicMock(return_value=User()))
        
        await register(mock_update, mock_context)
        
        # Проверка:
        # 1. Пользователь не добавлен
        mock_session.add.assert_not_called()
        
        # 2. Бот сообщает об ошибке
        mock_update.message.reply_text.assert_awaited_with("❌ Пользователь уже существует")

# Успешный вход в систему

@pytest.mark.asyncio
async def test_login_success(mock_update, mock_context):
    """Проверка входа с верными данными."""
    mock_context.args = ["test@example.com", "password123"]
    hashed_pw = bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode()
    
    with patch("handlers.AsyncSessionLocal", new_callable=AsyncMock) as mock_session:
        # Мок пользователя в БД
        mock_user = User(email="test@example.com", password_hash=hashed_pw)
        mock_session.return_value.__aenter__.return_value = mock_session
        mock_session.execute.return_value = MagicMock(scalar=MagicMock(return_value=mock_user))
        
        await login(mock_update, mock_context)
        
        # Проверка:
        # 1. Статус аутентификации обновлен
        assert mock_user.is_authenticated is True
        mock_session.commit.assert_awaited_once()
        
        # 2. Бот подтверждает вход
        mock_update.message.reply_text.assert_awaited_with("🔓 Вы успешно вошли в систему!")

# Неудачный вход с неверным паролем

@pytest.mark.asyncio
async def test_login_wrong_password(mock_update, mock_context):
    """Проверка ввода неверного пароля."""
    mock_context.args = ["test@example.com", "wrongpass"]
    hashed_pw = bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode()
    
    with patch("handlers.AsyncSessionLocal", new_callable=AsyncMock) as mock_session:
        # Мок пользователя в БД
        mock_user = User(email="test@example.com", password_hash=hashed_pw)
        mock_session.return_value.__aenter__.return_value = mock_session
        mock_session.execute.return_value = MagicMock(scalar=MagicMock(return_value=mock_user))
        
        await login(mock_update, mock_context)
        
        # Проверка:
        # 1. Статус аутентификации не изменился
        assert mock_user.is_authenticated is False
        
        # 2. Бот сообщает об ошибке
        mock_update.message.reply_text.assert_awaited_with("❌ Неверный email или пароль")

#Выход из системы

@pytest.mark.asyncio
async def test_logout(mock_update, mock_context):
    """Проверка выхода из системы."""
    with patch("handlers.AsyncSessionLocal", new_callable=AsyncMock) as mock_session:
        # Мок аутентифицированного пользователя
        mock_user = User(is_authenticated=True)
        mock_session.return_value.__aenter__.return_value = mock_session
        mock_session.execute.return_value = MagicMock(scalar=MagicMock(return_value=mock_user))
        
        await logout(mock_update, mock_context)
        
        # Проверка:
        # 1. Статус аутентификации сброшен
        assert mock_user.is_authenticated is False
        mock_session.commit.assert_awaited_once()
        
        # 2. Бот подтверждает выход
        mock_update.message.reply_text.assert_awaited_with("🔒 Вы вышли из системы")