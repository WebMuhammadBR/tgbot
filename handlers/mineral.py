from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from datetime import datetime

from excel_export import warehouse_expenses_to_excel, warehouse_receipts_to_excel
from keyboards import (
    warehouse_expense_districts_inline_keyboard,
    warehouse_movement_menu,
    warehouse_menu,
    warehouse_names_menu,
    warehouse_movements_pagination_keyboard,
    warehouse_products_inline_keyboard,
    warehouse_svod_products_inline_keyboard,
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
WAREHOUSE_SUMMARY_NAMES = {"📊 Свод", "svod", "свод"}
WAREHOUSE_EXPENSE_NAMES = {"📤 Чиқим", "chiqim", "чиқим"}


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




@router.message(F.text.func(lambda value: value and value.lower() in {name.lower() for name in WAREHOUSE_SUMMARY_NAMES}))
@access_required
async def warehouse_summary_products_handler(message: Message):
    warehouse_map = await _warehouse_map()
    warehouse_id = USER_SELECTED_WAREHOUSE.get(message.from_user.id)
    if not warehouse_id:
        await message.answer("Аввал омборни танланг", reply_markup=warehouse_names_menu(list(warehouse_map.values())))
        return

    warehouse_name = warehouse_map.get(warehouse_id, "Омбор")
    products = await get_warehouse_products(warehouse_id=warehouse_id, movement="out")
    if not products:
        await message.answer(f"🏬 {warehouse_name}\n\n📊 Свод учун маҳсулотлар топилмади.")
        return

    await message.answer(
        f"🏬 {warehouse_name}\n📊 Свод учун маҳсулотни танланг:",
        reply_markup=warehouse_svod_products_inline_keyboard(
            warehouse_id=warehouse_id,
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
        reply_markup=warehouse_expense_districts_inline_keyboard(warehouse_id, districts),
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
    _, warehouse_id, district_id = callback.data.split(":", maxsplit=2)
    warehouse_id = int(warehouse_id)
    district_id = int(district_id)

    warehouse_map = await _warehouse_map()
    warehouse_name = warehouse_map.get(warehouse_id, "Омбор")
    await _send_warehouse_products_page(
        message=callback.message,
        warehouse_id=warehouse_id,
        movement="out",
        district_id=district_id,
        warehouse_name=warehouse_name,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("warehouse_back_to_districts:"))
@access_required
async def warehouse_back_to_districts_handler(callback: CallbackQuery):
    _, warehouse_id = callback.data.split(":", maxsplit=1)
    warehouse_id = int(warehouse_id)
    warehouse_map = await _warehouse_map()
    warehouse_name = warehouse_map.get(warehouse_id, "Омбор")
    districts = await get_warehouse_expense_districts(warehouse_id=warehouse_id)

    await callback.message.edit_text(
        f"🏬 {warehouse_name}\n📤 Чиқим учун туманни танланг:",
        reply_markup=warehouse_expense_districts_inline_keyboard(warehouse_id, districts),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("warehouse_back_to_products:"))
@access_required
async def warehouse_back_to_products_handler(callback: CallbackQuery):
    _, warehouse_id, movement, district_id = callback.data.split(":", maxsplit=3)
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




@router.callback_query(F.data.startswith("warehouse_svod_product:"))
@access_required
async def warehouse_svod_product_handler(callback: CallbackQuery):
    _, warehouse_id, product_id = callback.data.split(":", maxsplit=2)
    warehouse_id = int(warehouse_id)
    product_id = int(product_id)

    movements = await get_warehouse_movements(
        movement="out",
        warehouse_id=warehouse_id,
        product_id=product_id,
    )

    grouped = {}
    for item in movements:
        district_name = str(item.get("district_name") or "-")
        quantity = float(item.get("quantity") or 0)
        grouped[district_name] = grouped.get(district_name, 0) + quantity

    products = await get_warehouse_products(warehouse_id=warehouse_id, movement="out")
    product_name = next(
        (item.get("product_name") for item in products if int(item.get("product_id", 0)) == product_id),
        "Маҳсулот",
    )

    warehouse_map = await _warehouse_map()
    warehouse_name = warehouse_map.get(warehouse_id, "Омбор")

    lines = [
        f"🏬 {warehouse_name}",
        f"📊 Свод: {product_name}",
        "",
        f"{'№':<3} {'Туман':<18} {'Ҳозирги кун':>11} {'Бир кунлик':>10} {'Мавсум':>10}",
        "-" * 58,
    ]

    if grouped:
        season_total = sum(grouped.values())
        for index, (district, value) in enumerate(sorted(grouped.items()), start=1):
            lines.append(f"{index:<3} {district[:18]:<18} {value:>11.0f} {value:>10.0f} {season_total:>10.0f}")
    else:
        lines.append("Маълумот топилмади.")

    keyboard = warehouse_svod_products_inline_keyboard(
        warehouse_id=warehouse_id,
        products=products,
        back_callback=f"warehouse_back_sections:{warehouse_id}",
    )

    content = "\n".join(lines)
    await callback.message.edit_text(f"<pre>{content}</pre>", parse_mode="HTML", reply_markup=keyboard)
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
        movement=movement,
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
        lines.append(f"{'Сана':<12} {'Нак-№':<5} {'Миқдори':>10}")
        lines.append("-" * 28)
        for item in page_items:
            date_text = _format_date_ddmmyyyy(item.get("date"))
            invoice_number = str(item.get("invoice_number") or "-")
            quantity = f"{float(item.get('quantity') or 0):.0f}"
            lines.append(f"{date_text:<14} {invoice_number:<7} {quantity:>5}")
    else:
        lines.append("📤 Чиқим деталлари:")
        lines.append(f"{'Сана':<12} {'Ҳужжат №':<10} {'Маҳсулот':<16} {'Миқдори':>8}")
        lines.append("-" * 52)
        for item in page_items:
            date_text = _format_date_ddmmyyyy(item.get("date"))
            document_number = str(item.get("number") or item.get("invoice_number") or "-")[:10]
            product = (item.get("product_name") or "-")[:16]
            quantity = f"{float(item.get('quantity') or 0):.0f}"
            lines.append(f"{date_text:<12} {document_number:<10} {product:<16} {quantity:>8}")

    content = "\n".join(lines)

    back_callback = f"warehouse_back_to_products:{warehouse_id}:{movement}:{district_id}"

    keyboard = warehouse_movements_pagination_keyboard(
        warehouse_id=warehouse_id,
        movement=movement,
        product_id=product_id,
        district_id=district_id,
        page=page,
        has_next=end < len(movements),
        back_callback=back_callback,
    )
    await message.edit_text(f"<pre>{content}</pre>", parse_mode="HTML", reply_markup=keyboard)


async def _send_warehouse_products_page(message, warehouse_id: int, movement: str, district_id: int, warehouse_name: str):
    district_filter = None if district_id == 0 else district_id
    products = await get_warehouse_products(
        warehouse_id=warehouse_id,
        movement=movement,
        district_id=district_filter,
    )

    if not products:
        if movement == "in":
            await message.edit_text(f"🏬 {warehouse_name}\n\n📥 Кирим бўйича маълумот топилмади.")
        else:
            await message.edit_text(f"🏬 {warehouse_name}\n\n📤 Чиқим бўйича маълумот топилмади.")
        return

    movement_token = f"out_d{district_id}" if movement == "out" else "in"
    back_callback = (
        f"warehouse_back_sections:{warehouse_id}"
        if movement == "in"
        else f"warehouse_back_to_districts:{warehouse_id}"
    )

    await message.edit_text(
        f"🏬 {warehouse_name}\n{'📥 Кирим' if movement == 'in' else '📤 Чиқим'} учун маҳсулотни танланг:",
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

    data = await get_warehouse_movements(
        movement=movement,
        warehouse_id=int(warehouse_id),
        product_id=int(product_id),
        district_id=None if int(district_id) == 0 else int(district_id),
    )

    if movement == "in":
        file_buffer = await warehouse_receipts_to_excel(data)
        filename = "warehouse_receipts.xlsx"
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

    data = await get_warehouse_movements(
        movement=actual_movement,
        warehouse_id=warehouse_id,
        district_id=district_id,
    )

    if actual_movement == "in":
        file_buffer = await warehouse_receipts_to_excel(data)
        filename = "warehouse_receipts.xlsx"
    else:
        file_buffer = await warehouse_expenses_to_excel(data)
        filename = "warehouse_expenses.xlsx"

    if not file_buffer:
        await callback.answer("Маълумот йўқ", show_alert=True)
        return

    file = BufferedInputFile(file_buffer.getvalue(), filename=filename)
    await callback.message.answer_document(document=file)
    await callback.answer()
