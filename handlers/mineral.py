from aiogram import F, Router
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
from services.api_client import (
    get_warehouse_expense_districts,
    get_warehouse_movements,
    get_warehouse_products,
    get_warehouse_totals_by_filters,
    get_warehouses,
)

router = Router()
PER_PAGE = 25
USER_SELECTED_WAREHOUSE: dict[int, int] = {}

WAREHOUSE_RECEIPT_NAMES = {"📥 Кирим", "kirim", "krim", "кирим"}
WAREHOUSE_EXPENSE_NAMES = {"📤 Чиқим", "chiqim", "чиқим"}
WAREHOUSE_REPORT_NAMES = {"📊 Свод", "svod", "свод"}


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


def _expense_rows_by_farmer(items: list[dict]) -> list[dict]:
    farmer_totals: dict[str, dict] = {}

    for item in items:
        farmer_name = (item.get("farmer_name") or "-").strip() or "-"
        quantity = float(item.get("quantity") or 0)
        maydon = float(item.get("maydon") or 0)

        record = farmer_totals.setdefault(
            farmer_name,
            {
                "farmer_name": farmer_name,
                "quantity": 0.0,
                "maydon": maydon,
            },
        )
        record["quantity"] += quantity

        if record.get("maydon", 0) <= 0 and maydon > 0:
            record["maydon"] = maydon

    rows = sorted(farmer_totals.values(), key=lambda row: row["farmer_name"])
    for row in rows:
        maydon = row.get("maydon") or 0
        row["quantity_per_area"] = (row["quantity"] / maydon) if maydon > 0 else 0.0

    return rows


async def _warehouse_map():
    warehouses = await get_warehouses()
    return {
        int(item["id"]): str(item.get("name", "")).strip()
        for item in warehouses
        if item.get("id") and str(item.get("name", "")).strip()
    }


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
    _, warehouse_id = callback.data.split(":", maxsplit=1)
    warehouse_id = int(warehouse_id)
    warehouse_map = await _warehouse_map()
    warehouse_name = warehouse_map.get(warehouse_id, "Омбор")

    await callback.message.edit_text(
        f"🏬 {warehouse_name}\nКеракли бўлимни танланг:\n\n📌 Кирим/Чиқимни пастдаги клавиатурадан танланг."
    )
    await callback.message.answer("Танланг 👇", reply_markup=warehouse_movement_menu())
    await callback.answer()


@router.callback_query(F.data.startswith("warehouse_expense_district:"))
@access_required
async def warehouse_expense_district_handler(callback: CallbackQuery):
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
    await callback.answer()


@router.callback_query(F.data.startswith("warehouse_back_to_districts:"))
@access_required
async def warehouse_back_to_districts_handler(callback: CallbackQuery):
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

    await callback.message.edit_text(
        f"🏬 {warehouse_name}\n{title}",
        reply_markup=warehouse_expense_districts_inline_keyboard(warehouse_id, districts, section=section),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("warehouse_back_to_products:"))
@access_required
async def warehouse_back_to_products_handler(callback: CallbackQuery):
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
    await callback.answer()


@router.callback_query(F.data.startswith("warehouse_product:"))
@access_required
async def warehouse_product_handler(callback: CallbackQuery):
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
    await callback.answer()


@router.callback_query(F.data.startswith("warehouse_movements_page:"))
@access_required
async def warehouse_movements_page_handler(callback: CallbackQuery):
    _, warehouse_id, movement, product_id, district_id, page = callback.data.split(":", maxsplit=5)
    await _send_warehouse_movements_page(
        message=callback.message,
        warehouse_id=int(warehouse_id),
        movement=movement,
        product_id=int(product_id),
        district_id=int(district_id),
        page=int(page),
    )
    await callback.answer()


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

    start = (page - 1) * PER_PAGE
    end = start + PER_PAGE
    page_items = movements[start:end]

    lines = [
        f"🏬 {warehouse_name}",
        f"📦 {product_name}",
        "",
        f"📥 Кирим: {float(totals.get('total_in', 0)):.2f}",
        f"📤 Чиқим: {float(totals.get('total_out', 0)):.2f}",
        f"🧮 Қолдиқ: {float(totals.get('balance', 0)):.2f}",
        "",
    ]

    if movement == "in":
        lines.append("📥 Кирим деталлари:")
        lines.append(f"{'Сана':<12} {'Юк-№':<4} {'Қоп':>4} {'Миқдори':>8}")
        lines.append("-" * 38)
        for item in page_items:
            date_text = _format_date_ddmmyyyy(item.get("date"))
            invoice_number = str(item.get("invoice_number") or "-")
            bag_count = f"{int(item.get('bag_count') or 0)}"
            quantity = f"{float(item.get('quantity') or 0):.0f}"
            lines.append(f"{date_text:<12} {invoice_number:<4} {bag_count:>4} {quantity:>8}")
    elif movement == "out":
        expense_rows = _expense_rows_by_farmer(movements)
        page_items = expense_rows[start:end]
        lines.append("📤 Чиқим деталлари:")
        lines.append(f"{'№':<3} {'Фермер номи':<16} {'Миқдори':>8} {'Га/кг':>6}")
        lines.append("-" * 37)
        for index, item in enumerate(page_items, start=start + 1):
            farmer_name = (item.get("farmer_name") or "-")[:16]
            quantity = f"{float(item.get('quantity') or 0):.0f}"
            per_area = f"{float(item.get('quantity_per_area') or 0):.0f}"
            lines.append(f"{index:<3} {farmer_name:<16} {quantity:>8} {per_area:>6}")
    else:
        report_rows = _report_rows_by_district(movements)
        page_items = report_rows[start:end]
        total_today_quantity = sum(float(item.get("today_quantity") or 0) for item in report_rows)
        total_quantity = sum(float(item.get("total_quantity") or 0) for item in report_rows)
        lines.append("📊 Свод деталлари:")
        today_title = date.today().strftime("%d.%m.%Y")
        lines.append(f"{'№':<3} {'Туман':<10} {'Бир кунда':>8} {'Мавсумда':>10}")
        lines.append(f"{'':<14} { today_title  :>10}")
        lines.append("-" * 40)
        for index, item in enumerate(page_items, start=start + 1):
            district_name = (item.get("district_name") or "-")[:16]
            today_quantity = f"{float(item.get('today_quantity') or 0):.0f}"
            district_total_quantity = f"{float(item.get('total_quantity') or 0):.0f}"
            lines.append(f"{index:<3} {district_name:<10} {today_quantity:>8} {district_total_quantity:>12}")

        lines.append("-" * 40)
        lines.append(f"{'':<3} {'Жами':<10} {total_today_quantity:>8.0f} {total_quantity:>10.0f}")

    content = "\n".join(lines)

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
    await message.edit_text(f"<pre>{content}</pre>", parse_mode="HTML", reply_markup=keyboard)


async def _send_warehouse_products_page(message, warehouse_id: int, movement: str, district_id: int, warehouse_name: str):
    district_filter = None if district_id == 0 else district_id
    products = await get_warehouse_products(
        warehouse_id=warehouse_id,
        movement="out" if movement == "report" else movement,
        district_id=district_filter,
    )

    if not products:
        if movement == "in":
            await message.edit_text(f"🏬 {warehouse_name}\n\n📥 Кирим бўйича маълумот топилмади.")
        elif movement == "out":
            await message.edit_text(f"🏬 {warehouse_name}\n\n📤 Чиқим бўйича маълумот топилмади.")
        else:
            await message.edit_text(f"🏬 {warehouse_name}\n\n📊 Свод бўйича маълумот топилмади.")
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

    await message.edit_text(
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
