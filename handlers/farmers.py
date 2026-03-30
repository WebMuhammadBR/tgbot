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
COTTON_PRICE = 7862


def _format_amount(value) -> str:
    amount = float(value or 0)
    amount_in_thousands = amount / 1000
    return f"{amount_in_thousands:,.1f}".replace(",", " ").replace(".", ",")


def _format_percent(value) -> str:
    return f"{float(value or 0):.1f}%".replace(".", ",")


def _to_float(value) -> float:
    return float(value or 0)


def _highlight_if_exceeds(value_text: str, current_value: float, limit_value: float) -> tuple[str, str] | str:
    return (value_text, "#d62828") if current_value > limit_value else value_text


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
            _format_amount(farmer.get("futures_quantity")),
            _format_amount(farmer.get("futures_amount")),
        ]
        row.extend(_format_amount(product_totals.get(product_name)) for product_name in product_names)

        total_advance_amount = _to_float(farmer.get("farmer_total_amount"))
        futures_amount = _to_float(farmer.get("futures_amount"))
        advance_percent = (total_advance_amount / futures_amount * 100) if futures_amount > 0 else 0
        required_cotton_qty = total_advance_amount / COTTON_PRICE if COTTON_PRICE else 0

        row.append(_format_amount(total_advance_amount))
        row.append(_highlight_if_exceeds(_format_percent(advance_percent), advance_percent, 60))
        row.append(_highlight_if_exceeds(_format_amount(required_cotton_qty), required_cotton_qty, _to_float(farmer.get("futures_quantity"))))
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

    columns = [
        "№",
        "Туман",
        "Массив",
        "Фермер номи",
        "Шартнома миқдори",
        "Шартнома суммаси",
        *product_names,
        "Жами",
        "Берилган бўнак \nшартноманинг (%) ни ташкил қилади",
        "Бўнакни қоплаш учун лозим бўлган пахта миқдори",
    ]
    column_widths = [80, 160, 160, 360, 220, 210, *([180] * len(product_names)), 170, 230, 230]
    column_alignments = [
        "center",
        "center",
        "center",
        "left",
        "center",
        "center",
        *( ["center"] * len(product_names)),
        "center",
        "center",
        "center",
    ]

    totals_by_product = []
    for product_name in product_names:
        total_value = sum(float((item.get("product_totals") or {}).get(product_name) or 0) for item in filtered_data)
        totals_by_product.append(_format_amount(total_value))

    grand_total = sum(_to_float(item.get("farmer_total_amount")) for item in filtered_data)
    futures_quantity_total = sum(_to_float(item.get("futures_quantity")) for item in filtered_data)
    futures_amount_total = sum(_to_float(item.get("futures_amount")) for item in filtered_data)
    total_advance_percent = (grand_total / futures_amount_total * 100) if futures_amount_total > 0 else 0
    total_required_cotton_qty = grand_total / COTTON_PRICE if COTTON_PRICE else 0

    rows.append(
        [
            "",
            "",
            "",
            "Жами",
            _format_amount(futures_quantity_total),
            _format_amount(futures_amount_total),
            *totals_by_product,
            _format_amount(grand_total),
            _highlight_if_exceeds(_format_percent(total_advance_percent), total_advance_percent, 60),
            _highlight_if_exceeds(_format_amount(total_required_cotton_qty), total_required_cotton_qty, futures_quantity_total),
        ]
    )

    image_bytes = build_table_image(
        title="📋 Фермер Баланс",
        subtitle=f"Туман: {district_title}",
        top_note="Минг сўмда",
        top_note_alignment="left",
        top_note_color="#d62828",
        header_groups=[
            {"title": "Берилган аванс", "span": len(product_names) + 1},
            {"title": "Таҳлил", "span": 2},
        ],
        row_span_columns=6,
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
