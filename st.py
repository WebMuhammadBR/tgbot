"""import aiohttp
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart

from .config import API_BASE_URL
from .keyboards import main_menu, farmers_pagination_keyboard,contracts_pagination_keyboard

router = Router()

PER_PAGE = 25  # 1 саҳифада 10 та фермер

from functools import wraps
from aiogram.types import Message, CallbackQuery


def access_required(handler):

    @wraps(handler)
    async def wrapper(event, *args, **kwargs):

        # Message ёки Callback ни аниқлаймиз
        if isinstance(event, Message):
            telegram_id = event.from_user.id
            full_name = event.from_user.full_name
        elif isinstance(event, CallbackQuery):
            telegram_id = event.from_user.id
            full_name = event.from_user.full_name
        else:
            return

        result = await check_access(
            telegram_id=telegram_id,
            full_name=full_name
        )

        if not result["allowed"]:
            if isinstance(event, Message):
                await event.answer("⛔️ Сизга рухсат берилмаган.")
            else:
                await event.answer("⛔️ Рухсат йўқ", show_alert=True)
            return

        return await handler(event, *args, **kwargs)

    return wrapper
#---------------------------------------------------------------------------------------------------

async def check_access(telegram_id: int, full_name: str):

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{API_BASE_URL}/bot-user/check/",
            json={
                "telegram_id": telegram_id,
                "full_name": full_name
            }
        ) as resp:
            data = await resp.json()
            return data

# ===============================
# 🔹 START
# ===============================

@router.message(CommandStart())
@access_required
async def start_handler(message: Message):

    result = await check_access(
        telegram_id=message.from_user.id,
        full_name=message.from_user.full_name
    )

    # Агар янги фойдаланувчи бўлса
    if result["created"]:
        await message.answer(
            "✅ Сиз рўйхатга қўшилдингиз.\n"
            "⏳ Админ тасдиқлаши кутилмоқда."
        )
        return

    # Агар active эмас бўлса
    if not result["allowed"]:
        await message.answer(
            "⛔️ Сиз ҳали тасдиқланмагансиз.\n"
            "Админ рухсат бериши керак."
        )
        return

    # Агар active бўлса
    await message.answer("Асосий меню 👇", reply_markup=main_menu)


# ===============================
# 🔹 FARMERS FIRST PAGE
# ===============================

@router.message(F.text == "📋 Фермерлар рўйхати")
@access_required
async def farmers_handler(message: Message):
    await send_farmers_page(message, page=1, edit=False)


# ===============================
# 🔹 CALLBACK PAGINATION
# ===============================

@router.callback_query(F.data.startswith("farmers_page:"))
@access_required
async def farmers_pagination(callback: CallbackQuery):
    page = int(callback.data.split(":")[1])
    await send_farmers_page(callback.message, page, edit=True)
    await callback.answer()



# ===============================
# 🔹 SEND PAGE FUNCTION
# ===============================

async def send_farmers_page(target, page: int, edit: bool = False):

    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE_URL}/farmers/") as resp:
            data = await resp.json()

    start = (page - 1) * PER_PAGE
    end = start + PER_PAGE
    page_data = data[start:end]

    if not page_data:
        return

    text = "📋 Фермерлар рўйхати\n\n"
    text += f"{'№':<3} {'Фермер номи':<20} {'Баланс':>15}\n"
    text += "-" * 45 + "\n"

    for index, farmer in enumerate(page_data, start=start + 1):
        text += (
            f"{index:<3} "
            f"{farmer['name'][:20]:<20} "
            f"{float(farmer['balance']):>15,.2f}\n"
        )

    has_next = end < len(data)
    keyboard = farmers_pagination_keyboard(page, has_next)

    if edit:
        # 🔥 Эски хабарни алмаштиради
        await target.edit_text(
            f"<pre>{text}</pre>",
            parse_mode="HTML",
            reply_markup=keyboard
        )
    else:
        # 🔥 Биринчи марта юбориш
        await target.answer(
            f"<pre>{text}</pre>",
            parse_mode="HTML",
            reply_markup=keyboard
        )











# ===============================
# 🔹 CONTRACTS FIRST PAGE
# ===============================

@router.message(F.text == "📑 Шартномалар")
@access_required
async def contracts_handler(message: Message):
    await send_contracts_page(message, page=1, edit=False)


# ===============================
# 🔹 CALLBACK PAGINATION
# ===============================

@router.callback_query(F.data.startswith("contracts_page:"))
@access_required
async def contracts_pagination(callback: CallbackQuery):
    page = int(callback.data.split(":")[1])
    await send_contracts_page(callback.message, page, edit=True)
    await callback.answer()


# ===============================
# 🔹 SEND PAGE FUNCTION
# ===============================

async def send_contracts_page(target, page: int, edit: bool = False):

    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE_URL}/farmers/summary/") as resp:
            data = await resp.json()

    start = (page - 1) * PER_PAGE
    end = start + PER_PAGE
    page_data = data[start:end]

    if not page_data:
        return

    text = "📑 Шартномалар рўйхати\n\n"
    text += f"{'№':<3} {'Фермер номи':<20} {'миқдор':>9} {'Сумма':>9}\n{' ':<3} {'           ':<20} {' (тн) ':>9} {'(млн)':>9}\n"
    text += "-" * 45 + "\n"

    for index, contract in enumerate(page_data, start=start + 1):
        text += (
            f"{index:<3} "
            f"{contract['name'][:20]:<20} "
            f"{float(contract['quantity']):>8,.1f}"
            f"{float(contract['amount']):>11,.0f}\n"
        )

    has_next = end < len(data)

    keyboard = contracts_pagination_keyboard(page, has_next)

    if edit:
        await target.edit_text(
            f"<pre>{text}</pre>",
            parse_mode="HTML",
            reply_markup=keyboard
        )
    else:
        await target.answer(
            f"<pre>{text}</pre>",
            parse_mode="HTML",
            reply_markup=keyboard
        )
"""