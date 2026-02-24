from aiogram import Router
from aiogram import F
from aiogram.types import Message
from aiogram.filters import CommandStart

from keyboards import main_menu, farmers_menu
from middlewares.access import access_required

router = Router()


@router.message(CommandStart())
@access_required
async def start_handler(message: Message):
    await message.answer("Асосий меню 👇", reply_markup=main_menu)


@router.message(F.text == "🏠 Асосий меню")
@access_required
async def back_to_main_menu(message: Message):
    await message.answer("Асосий меню 👇", reply_markup=main_menu)


@router.message(F.text == "📋 Фермерлар")
@access_required
async def farmers_menu_handler(message: Message):
    await message.answer("Фермерлар бўлими 👇", reply_markup=farmers_menu)
