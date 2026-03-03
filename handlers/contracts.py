from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from services.api_client import get_contracts_summary
from excel_export import contracts_to_excel
from keyboards import contracts_filter_keyboard, contracts_pagination_keyboard, contracts_type_menu, farmers_menu
from middlewares.access import access_required
from services.pagination import build_page_text, paginate_data

router = Router()
PER_PAGE = 25

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
    await callback.message.edit_text(
        "Туманни танланг 👇",
        reply_markup=contracts_filter_keyboard(districts, contract_type),
    )
    await callback.answer()


async def send_page(target, page, district_index, contract_type, edit):
    data = await get_contracts_data(contract_type)
    districts = extract_districts(data)
    district = get_district_by_index(districts, district_index)
    filtered_data = filter_by_district(data, district)
    page_data, start, end = paginate_data(filtered_data, page, PER_PAGE)

    district_title = "Ҳаммаси" if district == "all" else district
    type_title = CONTRACT_TYPE_LABELS.get(contract_type, "Ҳаммаси")

    text = build_page_text(
        title=f"📑 Шартномалар ({type_title}): {district_title}",
        headers=f"{'№':<3} {'Фермер номи':<14} {'миқдор':>7} {'Сумма':>7}",
        subheaders=f"{' ':<3} {'   ':<14} {'  (тн)':>4} {'   (млн)':>9}",
        rows=[
            (
                f"{index:<3} "
                f"{contract['name'][:14]:<14} "
                f"{float(contract['quantity']) / 1_000:>7,.1f}"
                f"{float(contract['amount']) / 1_000_000:>9,.1f}"
            )
            for index, contract in enumerate(page_data, start=start + 1)
        ],
    )

    keyboard = contracts_pagination_keyboard(page, end < len(filtered_data), district_index, contract_type)

    if edit:
        await target.edit_text(f"<pre>{text}</pre>", parse_mode="HTML", reply_markup=keyboard)
    else:
        await target.answer(f"<pre>{text}</pre>", parse_mode="HTML", reply_markup=keyboard)


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
        return await get_contracts_summary()
    return await get_contracts_summary(contract_type=contract_type)


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
