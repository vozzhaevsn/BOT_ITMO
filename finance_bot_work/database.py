from sqlalchemy import Column, Integer, String, JSON, Boolean
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True)
    email = Column(String(100), unique=True)
    password_hash = Column(String(200))
    is_authenticated = Column(Boolean, default=False)
    subscriptions = Column(JSON, default={"crypto": False, "stocks": False, "news": False})
    tracked_tickers = Column(JSON, default=[])

class NewsSubscription(Base):
    __tablename__ = 'news_subscriptions'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    query = Column(String(100))

engine = create_async_engine('sqlite+aiosqlite:///finance_bot.db', future=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)