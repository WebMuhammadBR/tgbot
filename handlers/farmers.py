from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile

from services.api_client import get_farmers
from excel_export import farmers_to_excel
from keyboards import farmers_filter_keyboard, farmers_pagination_keyboard
from middlewares.access import access_required
from services.pagination import paginate_data
from services.table_image import build_table_image, send_or_edit_table_image

router = Router()
PER_PAGE = 15


def _format_amount(value) -> str:
    amount = float(value or 0)
    amount_in_thousands = amount / 1000
    return f"{amount_in_thousands:,.1f}".replace(",", " ").replace(".", ",")


def _rows_with_dynamic_products(data: list[dict], start_index: int):
    product_names = sorted(
        {
            (name or "-").strip() or "-"
            for farmer in data
            for name in (farmer.get("product_totals") or {}).keys()
        },
        key=lambda value: value.lower(),
    )

    rows = []
    for index, farmer in enumerate(data, start=start_index):
        product_totals = farmer.get("product_totals") or {}
        row = [
            str(index),
            farmer.get("district") or "-",
            farmer.get("massive") or "-",
            farmer.get("name") or "-",
        ]
        row.extend(_format_amount(product_totals.get(product_name)) for product_name in product_names)
        row.append(_format_amount(farmer.get("farmer_total_amount")))
        rows.append(row)

    return product_names, rows


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

    # Previous bot response can be an image message (without text),
    # so editing text fails with: "there is no text in the message to edit".
    if callback.message.text:
        await callback.message.edit_text(
            "Туманни танланг 👇",
            reply_markup=farmers_filter_keyboard(districts),
        )
    else:
        await callback.message.answer(
            "Туманни танланг 👇",
            reply_markup=farmers_filter_keyboard(districts),
        )
        await callback.message.delete()

    await callback.answer()


async def send_page(target, page, district_index, edit):
    data = await get_farmers()
    districts = extract_districts(data)
    district = get_district_by_index(districts, district_index)
    filtered_data = sort_farmers(filter_by_district(data, district))
    page_data, start, end = paginate_data(filtered_data, page, PER_PAGE)

    district_title = "Умумий" if district == "all" else district

    product_names, rows = _rows_with_dynamic_products(page_data, start + 1)

    columns = ["№", "Туман", "Массив", "Фермер номи", *product_names, "Жами"]
    column_widths = [80, 160, 160, 360, *([180] * len(product_names)), 170]
    column_alignments = ["center", "left", "left", "left", *(["center"] * len(product_names)), "center"]

    totals_by_product = []
    for product_name in product_names:
        total_value = sum(float((item.get("product_totals") or {}).get(product_name) or 0) for item in filtered_data)
        totals_by_product.append(_format_amount(total_value))

    grand_total = sum(float(item.get("farmer_total_amount") or 0) for item in filtered_data)

    rows.append(["", "", "", "Жами", *totals_by_product, _format_amount(grand_total)])

    image_bytes = build_table_image(
        title="📋 Фермер Баланс",
        subtitle=f"Туман: {district_title}",
        top_note="Минг сўмда",
        top_note_alignment="left",
        top_note_color="#d62828",
        columns=columns,
        column_widths=column_widths,
        column_alignments=column_alignments,
        rows=rows,
        min_rows=PER_PAGE + 1,
    )

    keyboard = farmers_pagination_keyboard(page, end < len(filtered_data), district_index)
    await send_or_edit_table_image(target, image_bytes, keyboard, edit)


@router.callback_query(F.data.startswith("farmers_export_excel:"))
@access_required
async def farmers_excel(callback: CallbackQuery):
    district_index = int(callback.data.split(":", 1)[1])
    data = await get_farmers()
    districts = extract_districts(data)
    district = get_district_by_index(districts, district_index)
    filtered_data = sort_farmers(filter_by_district(data, district))

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


def sort_farmers(data: list[dict]) -> list[dict]:
    return sorted(
        data,
        key=lambda farmer: (
            (farmer.get("district") or "").lower(),
            (farmer.get("massive") or "").lower(),
            (farmer.get("contract") or "").lower(),
            -float(farmer.get("balance") or 0),
        )
    )


def get_district_by_index(districts: list[str], district_index: int) -> str:
    if district_index <= 0:
        return "all"
    district_pos = district_index - 1
    if district_pos >= len(districts):
        return "all"
    return districts[district_pos]
