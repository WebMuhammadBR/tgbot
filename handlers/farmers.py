from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile

from services.api_client import get_farmers
from excel_export import farmers_to_excel
from keyboards import farmers_filter_keyboard, farmers_pagination_keyboard
from middlewares.access import access_required
from services.pagination import build_page_text, paginate_data

router = Router()
PER_PAGE = 25


@router.message(F.text == "📋 Фермер Баланс")
@access_required
async def farmers_handler(message: Message):
    data = await get_farmers()
    districts = extract_districts(data)
    await message.answer("Туманни танланг 👇", reply_markup=farmers_filter_keyboard(districts))


@router.callback_query(F.data.startswith("farmers_filter:"))
@access_required
async def farmers_pagination(callback: CallbackQuery):
    _, district_index, page = callback.data.split(":", 2)
    await send_page(callback.message, int(page), int(district_index), True)
    await callback.answer()


@router.callback_query(F.data == "farmers_back_to_filters")
@access_required
async def farmers_back_to_filters(callback: CallbackQuery):
    data = await get_farmers()
    districts = extract_districts(data)
    await callback.message.edit_text("Туманни танланг 👇", reply_markup=farmers_filter_keyboard(districts))
    await callback.answer()


async def send_page(target, page, district_index, edit):
    data = await get_farmers()
    districts = extract_districts(data)
    district = get_district_by_index(districts, district_index)
    filtered_data = filter_by_district(data, district)
    page_data, start, end = paginate_data(filtered_data, page, PER_PAGE)

    district_title = "Умумий" if district == "all" else district

    text = build_page_text(
        title=f"📋 Фермер Баланс: {district_title}",
        headers=f"{'№':<3} {'Фермер номи':<18} {'Баланс':>13}",
        subheaders=f"{' ':<3} {' ':<18} {'(млн)':>13}",
        rows=[
            f"{index:<3} {farmer['name'][:18]:<18} {float(farmer['balance']) / 1_000_000:>13,.1f}"
            for index, farmer in enumerate(page_data, start=start + 1)
        ],
    )
    keyboard = farmers_pagination_keyboard(page, end < len(filtered_data), district_index)

    if edit:
        await target.edit_text(f"<pre>{text}</pre>", parse_mode="HTML", reply_markup=keyboard)
    else:
        await target.answer(f"<pre>{text}</pre>", parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data.startswith("farmers_export_excel:"))
@access_required
async def farmers_excel(callback: CallbackQuery):
    district_index = int(callback.data.split(":", 1)[1])
    data = await get_farmers()
    districts = extract_districts(data)
    district = get_district_by_index(districts, district_index)
    filtered_data = filter_by_district(data, district)

    file_buffer = await farmers_to_excel(filtered_data)

    if not file_buffer:
        await callback.answer("Маълумот йўқ", show_alert=True)
        return

    file = BufferedInputFile(
        file_buffer.getvalue(),
        filename="farmers.xlsx"
    )

    await callback.message.answer_document(
        document=file
    )

    await callback.answer()


def extract_districts(data: list[dict]) -> list[str]:
    districts = {
        farmer.get("district")
        for farmer in data
        if farmer.get("district")
    }
    return sorted(districts)


def filter_by_district(data: list[dict], district: str) -> list[dict]:
    if district == "all":
        return data
    return [farmer for farmer in data if farmer.get("district") == district]


def get_district_by_index(districts: list[str], district_index: int) -> str:
    if district_index <= 0:
        return "all"
    district_pos = district_index - 1
    if district_pos >= len(districts):
        return "all"
    return districts[district_pos]
