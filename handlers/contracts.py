from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from services.api_client import get_contracts_summary
from excel_export import contracts_to_excel
from keyboards import contracts_filter_keyboard, contracts_pagination_keyboard, contracts_type_menu, farmers_menu
from middlewares.access import access_required
from services.pagination import paginate_data
from services.table_image import build_table_image, send_or_edit_table_image

router = Router()
PER_PAGE = 15
FARMER_NAME_MAX_LENGTH = 22

CONTRACT_TYPE_ALL = "all"
CONTRACT_TYPE_MAP = {
    "📊 Ҳаммаси": CONTRACT_TYPE_ALL,
    "📑 Фючерс": "futures",
    "📑 Форвард": "forward",
    "📑 Сақлаш": "storage",
}
CONTRACT_TYPE_LABELS = {
    CONTRACT_TYPE_ALL: "Ҳаммаси",
    "futures": "Фючерс",
    "forward": "Форвард",
    "storage": "Сақлаш",
}


def _truncate_farmer_name(name: str | None) -> str:
    return (name or "-")[:FARMER_NAME_MAX_LENGTH]


@router.message(F.text == "📑 Шартномалар")
@access_required
async def contracts_handler(message: Message):
    await message.answer("Шартнома турини танланг 👇", reply_markup=contracts_type_menu)


@router.message(F.text.in_(set(CONTRACT_TYPE_MAP.keys())))
@access_required
async def contracts_type_selected(message: Message):
    contract_type = CONTRACT_TYPE_MAP[message.text]
    data = await get_contracts_data(contract_type)
    districts = extract_districts(data)
    await message.answer(
        "Туманни танланг 👇",
        reply_markup=contracts_filter_keyboard(districts, contract_type),
    )


@router.message(F.text == "⬅️ Фермерлар бўлими")
@access_required
async def back_to_farmers_menu(message: Message):
    await message.answer("Фермерлар бўлими 👇", reply_markup=farmers_menu)


@router.callback_query(F.data.startswith("contracts_filter:"))
@access_required
async def contracts_pagination(callback: CallbackQuery):
    _, contract_type, district_index, page = callback.data.split(":", 3)
    await send_page(callback.message, int(page), int(district_index), contract_type, True)
    await callback.answer()


@router.callback_query(F.data.startswith("contracts_back_to_districts:"))
@access_required
async def contracts_back_to_filters(callback: CallbackQuery):
    contract_type = callback.data.split(":", 1)[1]
    data = await get_contracts_data(contract_type)
    districts = extract_districts(data)
    await callback.message.answer(
        "Туманни танланг 👇",
        reply_markup=contracts_filter_keyboard(districts, contract_type),
    )
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await callback.answer()


async def send_page(target, page, district_index, contract_type, edit):
    data = await get_contracts_data(contract_type)
    districts = extract_districts(data)
    district = get_district_by_index(districts, district_index)
    filtered_data = filter_by_district(data, district)
    page_data, start, end = paginate_data(filtered_data, page, PER_PAGE)

    district_title = "Ҳаммаси" if district == "all" else district
    type_title = CONTRACT_TYPE_LABELS.get(contract_type, "Ҳаммаси")

    if contract_type == CONTRACT_TYPE_ALL:
        rows = [
            [
                str(index),
                contract["district"],
                contract["massive"],
                _truncate_farmer_name(contract["farmer_name"]),
                format_tons(contract["futures"]),
                format_tons(contract["forward"]),
                format_tons(contract["storage"]),
                format_tons(contract["total"]),
            ]
            for index, contract in enumerate(page_data, start=start + 1)
        ]

        totals = build_all_contracts_totals(filtered_data)
        rows.append(
            [
                "",
                "",
                "",
                "Жами",
                format_tons(totals["futures"]),
                format_tons(totals["forward"]),
                format_tons(totals["storage"]),
                format_tons(totals["total"]),
            ]
        )
        columns = ["№", "Туман", "Массив", "Фермер номи", "Фючерс", "Форвард", "Сақлаш", "Жами"]
        column_widths = [80, 160, 160, 380, 170, 170, 170, 170]
        column_alignments = ["center", "left", "left", "left", "center", "center", "center", "center"]
        min_rows = PER_PAGE + 1
    else:
        type_label = CONTRACT_TYPE_LABELS.get(contract_type, "Миқдор")
        rows = [
            [
                str(index),
                contract["district"],
                contract["massive"],
                _truncate_farmer_name(contract["farmer_name"]),
                format_tons(contract["quantity"]),
            ]
            for index, contract in enumerate(page_data, start=start + 1)
        ]
        total_quantity = sum(to_float(item.get("quantity")) for item in filtered_data)
        rows.append(["", "", "", "Жами", format_tons(total_quantity)])
        columns = ["№", "Туман", "Массив", "Фермер номи", type_label]
        column_widths = [120, 200, 200, 420, 210]
        column_alignments = ["center", "left", "left", "left", "center"]
        min_rows = PER_PAGE + 1

    image_bytes = build_table_image(
        title="📑 Шартномалар",
        subtitle=f"Тури: {type_title} | Туман: {district_title}",
        top_note="тоннада",
        top_note_alignment="left",
        top_note_color="#d62828",
        columns=columns,
        column_widths=column_widths,
        column_alignments=column_alignments,
        rows=rows,
        min_rows=min_rows,
    )

    keyboard = contracts_pagination_keyboard(page, end < len(filtered_data), district_index, contract_type)
    await send_or_edit_table_image(target, image_bytes, keyboard, edit)


@router.callback_query(F.data.startswith("contracts_export_excel:"))
@access_required
async def contracts_excel(callback: CallbackQuery):
    _, contract_type, district_index = callback.data.split(":", 2)
    data = await get_contracts_excel_data(contract_type)
    districts = extract_districts(data)
    district = get_district_by_index(districts, int(district_index))
    filtered_data = filter_by_district(data, district)

    file_buffer = await contracts_to_excel(filtered_data, contract_type=contract_type)

    if not file_buffer:
        await callback.answer("Маълумот йўқ", show_alert=True)
        return

    file = BufferedInputFile(
        file_buffer.getvalue(),
        filename="contracts.xlsx"
    )

    await callback.message.answer_document(
        document=file
    )

    await callback.answer()


async def get_contracts_data(contract_type: str):
    if contract_type == CONTRACT_TYPE_ALL:
        typed_data = {}
        for contract_key in ("futures", "forward", "storage"):
            typed_data[contract_key] = await get_contracts_summary(contract_type=contract_key)
        return aggregate_all_contract_types(typed_data)

    data = await get_contracts_summary(contract_type=contract_type)
    return aggregate_single_contract_type(data)


async def get_contracts_excel_data(contract_type: str):
    if contract_type != CONTRACT_TYPE_ALL:
        data = await get_contracts_summary(contract_type=contract_type)
        return [{**item, "contract_type": contract_type} for item in data]

    export_data = []
    for contract_key in ("futures", "forward", "storage"):
        typed_data = await get_contracts_summary(contract_type=contract_key)
        export_data.extend({**item, "contract_type": contract_key} for item in typed_data)

    return export_data


def extract_districts(data: list[dict]) -> list[str]:
    districts = {
        contract.get("district")
        for contract in data
        if contract.get("district")
    }
    return sorted(districts)


def filter_by_district(data: list[dict], district: str) -> list[dict]:
    if district == "all":
        return data
    return [contract for contract in data if contract.get("district") == district]


def get_district_by_index(districts: list[str], district_index: int) -> str:
    if district_index <= 0:
        return "all"
    district_pos = district_index - 1
    if district_pos >= len(districts):
        return "all"
    return districts[district_pos]


def aggregate_single_contract_type(data: list[dict]) -> list[dict]:
    grouped = {}

    for item in data:
        farmer_id = item.get("id")
        district = item.get("district") or "-"
        massive = item.get("massive") or "-"
        farmer_name = (item.get("farmer_name") or item.get("name") or "-").strip() or "-"
        key = farmer_id if farmer_id is not None else (district, massive, farmer_name)

        row = grouped.setdefault(
            key,
            {
                "district": district,
                "massive": massive,
                "farmer_name": farmer_name,
                "quantity": 0.0,
            },
        )
        row["quantity"] += to_float(item.get("quantity"))

    return sorted(grouped.values(), key=lambda row: (row["district"], row["massive"], row["farmer_name"]))


def aggregate_all_contract_types(typed_data: dict[str, list[dict]]) -> list[dict]:
    grouped = {}

    for contract_type, rows in typed_data.items():
        for item in rows:
            farmer_id = item.get("id")
            district = item.get("district") or "-"
            massive = item.get("massive") or "-"
            farmer_name = (item.get("farmer_name") or item.get("name") or "-").strip() or "-"
            key = farmer_id if farmer_id is not None else (district, massive, farmer_name)

            row = grouped.setdefault(
                key,
                {
                    "district": district,
                    "massive": massive,
                    "farmer_name": farmer_name,
                    "futures": 0.0,
                    "forward": 0.0,
                    "storage": 0.0,
                    "total": 0.0,
                },
            )
            quantity = to_float(item.get("quantity"))
            row[contract_type] += quantity
            row["total"] += quantity

    return sorted(grouped.values(), key=lambda row: (row["district"], row["massive"], row["farmer_name"]))


def build_all_contracts_totals(data: list[dict]) -> dict[str, float]:
    totals = {
        "futures": 0.0,
        "forward": 0.0,
        "storage": 0.0,
        "total": 0.0,
    }

    for item in data:
        totals["futures"] += to_float(item.get("futures"))
        totals["forward"] += to_float(item.get("forward"))
        totals["storage"] += to_float(item.get("storage"))
        totals["total"] += to_float(item.get("total"))

    return totals


def to_float(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def format_tons(value) -> str:
    return f"{to_float(value):,.1f}".replace(",", " ").replace(".", ",")
