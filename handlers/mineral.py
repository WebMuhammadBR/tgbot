from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from datetime import date, datetime

from excel_export import warehouse_expenses_to_excel, warehouse_receipts_to_excel
from keyboards import (
    warehouse_expense_districts_inline_keyboard,
    warehouse_movement_menu,
    warehouse_menu,
    warehouse_names_menu,
    warehouse_movements_pagination_keyboard,
    warehouse_products_inline_keyboard,
)
from middlewares.access import access_required
from services.table_image import build_table_image, send_or_edit_table_image
from services.api_client import (
    get_warehouse_expense_districts,
    get_warehouse_movements,
    get_warehouse_products,
    get_warehouse_summary,
    get_warehouse_totals_by_filters,
    get_warehouses,
)

router = Router()
PER_PAGE = 10
REPORT_PER_PAGE = 6
FARMER_NAME_MAX_LENGTH = 22
USER_SELECTED_WAREHOUSE: dict[int, int] = {}

WAREHOUSE_RECEIPT_NAMES = {"📥 Кирим", "kirim", "krim", "кирим"}
WAREHOUSE_EXPENSE_NAMES = {"📤 Чиқим", "chiqim", "чиқим"}
WAREHOUSE_REPORT_NAMES = {"📊 Свод", "svod", "свод"}
WAREHOUSE_TOTAL_NAME = "📊 Жами омбор"


async def _edit_message_content(message: Message, text: str, reply_markup=None):
    if message.content_type == "photo":
        try:
            await message.delete()
            await message.answer(text, reply_markup=reply_markup)
            return
        except TelegramBadRequest:
            pass

    await message.edit_text(text, reply_markup=reply_markup)


def _format_date_ddmmyyyy(value) -> str:
    if not value:
        return "-"

    date_text = str(value).strip()
    normalized = date_text.replace("Z", "+00:00")

    try:
        return datetime.fromisoformat(normalized).strftime("%d.%m.%Y")
    except ValueError:
        pass

    for date_format in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(date_text[:10], date_format).strftime("%d.%m.%Y")
        except ValueError:
            continue

    return date_text[:10]

def _date_key(value) -> str:
    if not value:
        return ""

    date_text = str(value).strip()
    normalized = date_text.replace("Z", "+00:00")

    try:
        return datetime.fromisoformat(normalized).strftime("%Y-%m-%d")
    except ValueError:
        pass

    for date_format in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(date_text[:10], date_format).strftime("%Y-%m-%d")
        except ValueError:
            continue

    return date_text[:10]


def _format_number_with_spaces(value, digits: int = 0) -> str:
    formatted = f"{float(value or 0):,.{digits}f}"
    return formatted.replace(",", " ")


def _report_rows_by_district(items: list[dict]) -> list[dict]:
    today_key = date.today().strftime("%Y-%m-%d")
    district_totals: dict[str, dict] = {}

    for item in items:
        district_name = (item.get("district_name") or "-").strip() or "-"
        quantity = float(item.get("quantity") or 0)
        record = district_totals.setdefault(
            district_name,
            {"district_name": district_name, "today_quantity": 0.0, "total_quantity": 0.0},
        )
        record["total_quantity"] += quantity

        if _date_key(item.get("date")) == today_key:
            record["today_quantity"] += quantity

    return sorted(district_totals.values(), key=lambda row: row["district_name"])


def _aggregate_expense_rows_by_farmer(items: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str, str, str], dict] = {}

    for item in items:
        district_name = (item.get("district_name") or "-").strip() or "-"
        massive_name = (item.get("massive_name") or "-").strip() or "-"
        farmer_name = (item.get("farmer_name") or "-").strip() or "-"
        product_name = (item.get("product_name") or "-").strip() or "-"

        key = (district_name, massive_name, farmer_name, product_name)
        quantity = float(item.get("quantity") or 0)

        row = grouped.setdefault(
            key,
            {
                "district_name": district_name,
                "massive_name": massive_name,
                "farmer_name": farmer_name,
                "product_name": product_name,
                "quantity": 0.0,
                "maydon": float(item.get("maydon") or 0),
                "quantity_per_area": 0.0,
            },
        )
        row["quantity"] += quantity
        row["maydon"] = max(row["maydon"], float(item.get("maydon") or 0))
        row["quantity_per_area"] = row["quantity"] / row["maydon"] if row["maydon"] > 0 else 0.0

    return sorted(
        grouped.values(),
        key=lambda row: (row["district_name"], row["massive_name"], row["farmer_name"], row["product_name"]),
    )


async def _warehouse_map():
    warehouses = await get_warehouses()
    return {
        int(item["id"]): str(item.get("name", "")).strip()
        for item in warehouses
        if item.get("id") and str(item.get("name", "")).strip()
    }


def _warehouse_summary_table_config(summary: dict) -> tuple[list[str], list[int], list[str], list[list[str]], list[dict]]:
    products = summary.get("products") or []
    rows = summary.get("rows") or []
    totals = summary.get("totals") or {"warehouse_name": "Жами", "products": []}

    columns = ["№", "Омбор\u00a0номи"]
    column_widths = [70, 250]
    column_alignments = ["center", "left"]
    header_groups = []

    for product in products:
        product_name = str(product.get("product_name") or "Маҳсулот")
        header_groups.append({"title": product_name, "span": 3})
        columns.extend(["Кирим", "Чиқим", "Қолдиқ"])
        column_widths.extend([120, 120, 120])
        column_alignments.extend(["center", "center", "center"])

    table_rows: list[list[str]] = []
    for row in rows:
        line = [str(row.get("order") or ""), str(row.get("warehouse_name") or "-")]
        products_data = {
            int(item.get("product_id")): item
            for item in row.get("products") or []
            if item.get("product_id")
        }
        for product in products:
            product_totals = products_data.get(int(product["product_id"]), {})
            line.extend(
                [
                    _format_number_with_spaces(product_totals.get("total_in", 0), digits=0),
                    _format_number_with_spaces(product_totals.get("total_out", 0), digits=0),
                    _format_number_with_spaces(product_totals.get("balance", 0), digits=0),
                ]
            )
        table_rows.append(line)

    totals_data = {
        int(item.get("product_id")): item
        for item in totals.get("products") or []
        if item.get("product_id")
    }
    totals_line = ["", str(totals.get("warehouse_name") or "Жами")]
    for product in products:
        product_totals = totals_data.get(int(product["product_id"]), {})
        totals_line.extend(
            [
                _format_number_with_spaces(product_totals.get("total_in", 0), digits=0),
                _format_number_with_spaces(product_totals.get("total_out", 0), digits=0),
                _format_number_with_spaces(product_totals.get("balance", 0), digits=0),
            ]
        )
    table_rows.append(totals_line)

    return columns, column_widths, column_alignments, table_rows, header_groups


@router.message(F.text.in_({"🌾 Минерал ўғит", "🏬 Омбор"}))
@access_required
async def mineral_menu_handler(message: Message):
    warehouse_map = await _warehouse_map()
    if not warehouse_map:
        await message.answer("Омборлар топилмади. Қуйидаги тугмалардан фойдаланинг 👇", reply_markup=warehouse_menu)
        return

    await message.answer(
        "🏬 Омборлар рўйхати 👇",
        reply_markup=warehouse_names_menu(list(warehouse_map.values())),
    )


@router.message(F.text == "⬅️ Омборлар рўйхати")
@access_required
async def back_to_warehouses_handler(message: Message):
    warehouse_map = await _warehouse_map()
    await message.answer(
        "🏬 Омборлар рўйхати 👇",
        reply_markup=warehouse_names_menu(list(warehouse_map.values())),
    )


@router.message(F.text == WAREHOUSE_TOTAL_NAME)
@access_required
async def warehouse_total_summary_handler(message: Message):
    summary = await get_warehouse_summary()
    products = summary.get("products") or []
    rows = summary.get("rows") or []
    if not products or not rows:
        await message.answer("📊 Жами омбор бўйича маълумот топилмади.")
        return

    columns, column_widths, column_alignments, table_rows, header_groups = _warehouse_summary_table_config(summary)
    image_bytes = build_table_image(
        title="🏬 Жами омборлар ҳисоботи",
        columns=columns,
        column_widths=column_widths,
        column_alignments=column_alignments,
        rows=table_rows,
        header_groups=header_groups,
        row_span_columns=2,
        min_rows=len(table_rows),
    )
    await message.answer_photo(photo=BufferedInputFile(image_bytes, filename="warehouse_summary.png"))


@router.message(F.text.func(lambda value: value and value.lower() in {name.lower() for name in WAREHOUSE_RECEIPT_NAMES}))
@access_required
async def warehouse_receipt_products_handler(message: Message):
    warehouse_map = await _warehouse_map()
    warehouse_id = USER_SELECTED_WAREHOUSE.get(message.from_user.id)
    if not warehouse_id:
        await message.answer("Аввал омборни танланг", reply_markup=warehouse_names_menu(list(warehouse_map.values())))
        return

    warehouse_name = warehouse_map.get(warehouse_id, "Омбор")
    products = await get_warehouse_products(warehouse_id=warehouse_id, movement="in")
    if not products:
        await message.answer(f"🏬 {warehouse_name}\n\n📥 Кирим бўйича маълумот топилмади.")
        return

    await message.answer(
        f"🏬 {warehouse_name}\n📥 Кирим учун маҳсулотни танланг:",
        reply_markup=warehouse_products_inline_keyboard(
            warehouse_id=warehouse_id,
            movement="in",
            products=products,
            back_callback=f"warehouse_back_sections:{warehouse_id}",
        ),
    )




@router.message(F.text.func(lambda value: value and value.lower() in {name.lower() for name in WAREHOUSE_REPORT_NAMES}))
@access_required
async def warehouse_report_districts_handler(message: Message):
    warehouse_map = await _warehouse_map()
    warehouse_id = USER_SELECTED_WAREHOUSE.get(message.from_user.id)
    if not warehouse_id:
        await message.answer("Аввал омборни танланг", reply_markup=warehouse_names_menu(list(warehouse_map.values())))
        return

    warehouse_name = warehouse_map.get(warehouse_id, "Омбор")
    products = await get_warehouse_products(warehouse_id=warehouse_id, movement="out")
    if not products:
        await message.answer(f"🏬 {warehouse_name}\n\n📊 Свод бўйича маълумот топилмади.")
        return

    await message.answer(
        f"🏬 {warehouse_name}\n📊 Свод учун маҳсулотни танланг:",
        reply_markup=warehouse_products_inline_keyboard(
            warehouse_id=warehouse_id,
            movement="report",
            products=products,
            back_callback=f"warehouse_back_sections:{warehouse_id}",
        ),
    )


@router.message(F.text.func(lambda value: value and value.lower() in {name.lower() for name in WAREHOUSE_EXPENSE_NAMES}))
@access_required
async def warehouse_expense_districts_handler(message: Message):
    warehouse_map = await _warehouse_map()
    warehouse_id = USER_SELECTED_WAREHOUSE.get(message.from_user.id)
    if not warehouse_id:
        await message.answer("Аввал омборни танланг", reply_markup=warehouse_names_menu(list(warehouse_map.values())))
        return

    warehouse_name = warehouse_map.get(warehouse_id, "Омбор")
    districts = await get_warehouse_expense_districts(warehouse_id=warehouse_id)
    if not districts:
        await message.answer(f"🏬 {warehouse_name}\n\nЧиқим бўйича туманлар топилмади.")
        return

    await message.answer(
        f"🏬 {warehouse_name}\n📤 Чиқим учун туманни танланг:",
        reply_markup=warehouse_expense_districts_inline_keyboard(warehouse_id, districts, section="out"),
    )


@router.message(F.text.func(lambda value: bool(value)))
@access_required
async def warehouse_item_handler(message: Message):
    warehouse_map = await _warehouse_map()
    selected = (message.text or "").strip()

    warehouse_id = next((wid for wid, name in warehouse_map.items() if name == selected), None)
    if not warehouse_id:
        return

    USER_SELECTED_WAREHOUSE[message.from_user.id] = warehouse_id

    await message.answer(
        f"🏬 {selected}\nКеракли бўлимни танланг:",
        reply_markup=warehouse_movement_menu(),
    )


@router.callback_query(F.data.startswith("warehouse_back_sections:"))
@access_required
async def warehouse_back_sections_handler(callback: CallbackQuery):
    await callback.answer()
    _, warehouse_id = callback.data.split(":", maxsplit=1)
    warehouse_id = int(warehouse_id)
    warehouse_map = await _warehouse_map()
    warehouse_name = warehouse_map.get(warehouse_id, "Омбор")

    await _edit_message_content(
        callback.message,
        f"🏬 {warehouse_name}\nКеракли бўлимни танланг:\n\n📌 Кирим/Чиқимни пастдаги клавиатурадан танланг."
    )
    await callback.message.answer("Танланг 👇", reply_markup=warehouse_movement_menu())


@router.callback_query(F.data.startswith("warehouse_expense_district:"))
@access_required
async def warehouse_expense_district_handler(callback: CallbackQuery):
    await callback.answer()
    _, warehouse_id, district_id, section = callback.data.split(":", maxsplit=3)
    warehouse_id = int(warehouse_id)
    district_id = int(district_id)

    warehouse_map = await _warehouse_map()
    warehouse_name = warehouse_map.get(warehouse_id, "Омбор")
    movement = "report" if section == "report" else "out"
    await _send_warehouse_products_page(
        message=callback.message,
        warehouse_id=warehouse_id,
        movement=movement,
        district_id=district_id,
        warehouse_name=warehouse_name,
    )


@router.callback_query(F.data.startswith("warehouse_back_to_districts:"))
@access_required
async def warehouse_back_to_districts_handler(callback: CallbackQuery):
    await callback.answer()
    parts = callback.data.split(":", maxsplit=2)
    warehouse_id = int(parts[1])
    section = parts[2] if len(parts) > 2 else "out"
    warehouse_map = await _warehouse_map()
    warehouse_name = warehouse_map.get(warehouse_id, "Омбор")
    districts = await get_warehouse_expense_districts(warehouse_id=warehouse_id)

    if section == "report":
        title = "📊 Свод учун туманни танланг:"
    else:
        title = "📤 Чиқим учун туманни танланг:"

    await _edit_message_content(
        callback.message,
        f"🏬 {warehouse_name}\n{title}",
        reply_markup=warehouse_expense_districts_inline_keyboard(warehouse_id, districts, section=section),
    )


@router.callback_query(F.data.startswith("warehouse_back_to_products:"))
@access_required
async def warehouse_back_to_products_handler(callback: CallbackQuery):
    await callback.answer()
    _, warehouse_id, movement, district_id, section = callback.data.split(":", maxsplit=4)
    warehouse_id = int(warehouse_id)
    district_id = int(district_id)

    warehouse_map = await _warehouse_map()
    warehouse_name = warehouse_map.get(warehouse_id, "Омбор")
    await _send_warehouse_products_page(
        message=callback.message,
        warehouse_id=warehouse_id,
        movement=movement,
        district_id=district_id,
        warehouse_name=warehouse_name,
    )


@router.callback_query(F.data.startswith("warehouse_product:"))
@access_required
async def warehouse_product_handler(callback: CallbackQuery):
    await callback.answer()
    _, warehouse_id, movement, product_id = callback.data.split(":", maxsplit=3)
    warehouse_id = int(warehouse_id)
    product_id = int(product_id)

    district_id = None
    actual_movement = movement
    if movement.startswith("out_d"):
        actual_movement = "out"
        district_id = int(movement.removeprefix("out_d"))
    elif movement.startswith("report_d"):
        actual_movement = "report"
        district_id = int(movement.removeprefix("report_d"))

    await _send_warehouse_movements_page(
        message=callback.message,
        warehouse_id=warehouse_id,
        movement=actual_movement,
        product_id=product_id,
        district_id=district_id or 0,
        page=1,
    )


@router.callback_query(F.data.startswith("warehouse_movements_page:"))
@access_required
async def warehouse_movements_page_handler(callback: CallbackQuery):
    await callback.answer()
    _, warehouse_id, movement, product_id, district_id, page = callback.data.split(":", maxsplit=5)
    await _send_warehouse_movements_page(
        message=callback.message,
        warehouse_id=int(warehouse_id),
        movement=movement,
        product_id=int(product_id),
        district_id=int(district_id),
        page=int(page),
    )


async def _send_warehouse_movements_page(
    message,
    warehouse_id: int,
    movement: str,
    product_id: int,
    district_id: int,
    page: int,
):
    totals = await get_warehouse_totals_by_filters(
        warehouse_id=warehouse_id,
        product_id=product_id,
        district_id=None if district_id == 0 else district_id,
    )
    movements = await get_warehouse_movements(
        movement=movement,
        warehouse_id=warehouse_id,
        product_id=product_id,
        district_id=None if district_id == 0 else district_id,
    )
    warehouse_map = await _warehouse_map()
    warehouse_name = warehouse_map.get(warehouse_id, "Омбор")

    products = await get_warehouse_products(
        warehouse_id=warehouse_id,
        movement="out" if movement == "report" else movement,
        district_id=None if district_id == 0 else district_id,
    )
    product_name = next(
        (item.get("product_name") for item in products if int(item.get("product_id", 0)) == product_id),
        "Маҳсулот",
    )

    page_size = REPORT_PER_PAGE if movement == "report" else PER_PAGE
    start = (page - 1) * page_size
    end = start + page_size
    page_items = movements[start:end]

    subtitle = (
        f"Омбор: {warehouse_name}  |  Маҳсулот: {product_name}"[:140]
        + "\n\n"
        + (
            f"Кирим: {_format_number_with_spaces(totals.get('total_in', 0), digits=2)}  |  "
            f"Чиқим: {_format_number_with_spaces(totals.get('total_out', 0), digits=2)}  |  "
            f"Қолдиқ: {_format_number_with_spaces(totals.get('balance', 0), digits=2)}"
        )
    )

    footer_lines = None
    report_rows: list[dict] = []
    expense_rows: list[dict] = []

    if movement == "in":
        table_title = "📥 Кирим деталлари"
        columns = ["№", "Юк-хати №", "Маҳсулот", "Транспорт №", "Қоп сони", "Миқдори", "Омбор"]
        column_widths = [80, 170, 220, 180, 150, 150, 210]
        rows = [
            [
                str(index),
                str(item.get("invoice_number") or "-"),
                str(item.get("product_name") or "-"),
                str(item.get("transport_number") or "-"),
                _format_number_with_spaces(item.get("bag_count") or 0),
                _format_number_with_spaces(item.get("quantity") or 0),
                str(item.get("warehouse_name") or "-"),
            ]
            for index, item in enumerate(page_items, start=start + 1)
        ]
        column_alignments = ["center", "center", "left", "center", "center", "center", "left"]
    elif movement == "out":
        expense_rows = _aggregate_expense_rows_by_farmer(movements)
        page_items = expense_rows[start:end]
        table_title = "📤 Чиқим деталлари"
        columns = ["№", "Туман", "Массив", "Фермер номи", "Маҳсулот", "Миқдори", "Га/кг"]
        column_widths = [70, 150, 160, 320, 180, 150, 150]
        column_alignments = ["center", "left", "left", "left", "left", "center", "center"]
        rows = [
            [
                str(index),
                (item.get("district_name") or "-")[:16],
                (item.get("massive_name") or "-")[:16],
                (item.get("farmer_name") or "-")[:FARMER_NAME_MAX_LENGTH],
                (item.get("product_name") or "-")[:16],
                _format_number_with_spaces(item.get("quantity") or 0),
                (
                    _format_number_with_spaces(item.get("quantity_per_area") or 0),
                    "#d62828",
                )
                if float(item.get("quantity_per_area") or 0) > 302
                else _format_number_with_spaces(item.get("quantity_per_area") or 0),
            ]
            for index, item in enumerate(page_items, start=start + 1)
        ]
    else:
        report_rows = _report_rows_by_district(movements)
        page_items = report_rows[start:end]
        total_today_quantity = sum(float(item.get("today_quantity") or 0) for item in report_rows)
        total_quantity = sum(float(item.get("total_quantity") or 0) for item in report_rows)

        table_title = "Свод деталлари"
        columns = ["№", "Туман", "Бир кунда ", "Мавсумда"]
        column_widths = [100, 300, 290, 250]
        column_alignments = ["center", "left", "center", "center"]
        rows = [
            [
                str(index),
                (item.get("district_name") or "-")[:24],
                _format_number_with_spaces(item.get("today_quantity") or 0),
                _format_number_with_spaces(item.get("total_quantity") or 0),
            ]
            for index, item in enumerate(page_items, start=start + 1)
        ]
        rows.append(
            [
                "",
                "ЖАМИ",
                _format_number_with_spaces(total_today_quantity),
                _format_number_with_spaces(total_quantity),
            ]
        )
        footer_lines = [
            f"Жами бир кунда: {_format_number_with_spaces(total_today_quantity)}",
            f"Жами мавсумда: {_format_number_with_spaces(total_quantity)}",
        ]

    top_note = f"Сана: {date.today().strftime('%d.%m.%Y')}" if movement == "report" else None

    image_bytes = build_table_image(
        title=table_title,
        subtitle=subtitle,
        subtitle_bold=True,
        subtitle_color="#0b1f44",
        subtitle_alignment="left",
        top_note=top_note,
        top_note_alignment="left",
        top_note_right_padding=70,
        top_note_bold=True,
        top_note_color="#d62828",
        columns=columns,
        column_widths=column_widths,
        column_alignments=column_alignments,
        rows=rows,
        min_rows=page_size,
        footer_lines=footer_lines,
    )

    section = "report" if movement == "report" else movement
    back_callback = f"warehouse_back_to_products:{warehouse_id}:{movement}:{district_id}:{section}"

    keyboard = warehouse_movements_pagination_keyboard(
        warehouse_id=warehouse_id,
        movement=movement,
        product_id=product_id,
        district_id=district_id,
        page=page,
        has_next=end < (
            len(report_rows)
            if movement == "report"
            else (len(expense_rows) if movement == "out" else len(movements))
        ),
        back_callback=back_callback,
    )
    await send_or_edit_table_image(message, image_bytes, keyboard, edit=True)


async def _send_warehouse_products_page(message, warehouse_id: int, movement: str, district_id: int, warehouse_name: str):
    district_filter = None if district_id == 0 else district_id
    products = await get_warehouse_products(
        warehouse_id=warehouse_id,
        movement="out" if movement == "report" else movement,
        district_id=district_filter,
    )

    if not products:
        if movement == "in":
            await _edit_message_content(message, f"🏬 {warehouse_name}\n\n📥 Кирим бўйича маълумот топилмади.")
        elif movement == "out":
            await _edit_message_content(message, f"🏬 {warehouse_name}\n\n📤 Чиқим бўйича маълумот топилмади.")
        else:
            await _edit_message_content(message, f"🏬 {warehouse_name}\n\n📊 Свод бўйича маълумот топилмади.")
        return

    movement_token = "in"
    section = "in"
    if movement == "out":
        movement_token = f"out_d{district_id}"
        section = "out"
    elif movement == "report":
        movement_token = "report"
        section = "report"

    back_callback = (
        f"warehouse_back_sections:{warehouse_id}"
        if movement in {"in", "report"}
        else f"warehouse_back_to_districts:{warehouse_id}:{section}"
    )

    section_title = "📥 Кирим" if movement == "in" else ("📤 Чиқим" if movement == "out" else "📊 Свод")

    await _edit_message_content(
        message,
        f"🏬 {warehouse_name}\n{section_title} учун маҳсулотни танланг:",
        reply_markup=warehouse_products_inline_keyboard(
            warehouse_id,
            movement_token,
            products,
            back_callback=back_callback,
        ),
    )


@router.callback_query(F.data.startswith("warehouse_export_filtered:"))
@access_required
async def warehouse_export_filtered_handler(callback: CallbackQuery):
    _, warehouse_id, movement, product_id, district_id = callback.data.split(":", maxsplit=4)

    actual_movement = movement
    data = await get_warehouse_movements(
        movement=actual_movement,
        warehouse_id=int(warehouse_id),
        product_id=int(product_id),
        district_id=None if int(district_id) == 0 else int(district_id),
    )

    if movement == "in":
        file_buffer = await warehouse_receipts_to_excel(data)
        filename = "warehouse_receipts.xlsx"
    elif movement == "report":
        file_buffer = await warehouse_expenses_to_excel(_report_rows_by_district(data), mode="report")
        filename = "warehouse_report.xlsx"
    else:
        file_buffer = await warehouse_expenses_to_excel(data)
        filename = "warehouse_expenses.xlsx"

    if not file_buffer:
        await callback.answer("Маълумот йўқ", show_alert=True)
        return

    file = BufferedInputFile(file_buffer.getvalue(), filename=filename)
    await callback.message.answer_document(document=file)
    await callback.answer()


@router.callback_query(F.data.startswith("warehouse_export:"))
@access_required
async def warehouse_export_handler(callback: CallbackQuery):
    _, warehouse_id, movement = callback.data.split(":", maxsplit=2)
    warehouse_id = int(warehouse_id)
    district_id = None
    actual_movement = movement
    if movement.startswith("out_d"):
        actual_movement = "out"
        district_id = int(movement.removeprefix("out_d"))
    elif movement.startswith("report_d"):
        actual_movement = "report"
        district_id = int(movement.removeprefix("report_d"))

    data = await get_warehouse_movements(
        movement=actual_movement,
        warehouse_id=warehouse_id,
        district_id=district_id,
    )

    if actual_movement == "in":
        file_buffer = await warehouse_receipts_to_excel(data)
        filename = "warehouse_receipts.xlsx"
    elif actual_movement == "report":
        file_buffer = await warehouse_expenses_to_excel(_report_rows_by_district(data), mode="report")
        filename = "warehouse_report.xlsx"
    else:
        file_buffer = await warehouse_expenses_to_excel(data)
        filename = "warehouse_expenses.xlsx"

    if not file_buffer:
        await callback.answer("Маълумот йўқ", show_alert=True)
        return

    file = BufferedInputFile(file_buffer.getvalue(), filename=filename)
    await callback.message.answer_document(document=file)
    await callback.answer()
