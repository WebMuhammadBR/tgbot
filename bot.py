import asyncio
from aiogram import Bot, Dispatcher

from config import TOKEN
from handlers import start, farmers, contracts, mineral

bot = Bot(token=TOKEN)
dp = Dispatcher()

dp.include_router(start.router)
dp.include_router(farmers.router)
dp.include_router(contracts.router)
dp.include_router(mineral.router)


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

