#11111111111111111111111111
from io import BytesIO
from datetime import datetime
import pandas as pd
from openpyxl.styles import Font


def _as_int_amount(value):
    return int(float(value or 0))


def _as_percent(value):
    return round(float(value or 0), 2)


COTTON_PRICE = 7862

def _excel_date(value):
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


def _autosize_and_bold(worksheet):
    for cell in worksheet[1]:
        cell.font = Font(bold=True)

    for column in worksheet.columns:
        max_length = 0
        column_letter = column[0].column_letter

        for cell in column:
            value = cell.value
            if value is not None:
                max_length = max(max_length, len(str(value)))

        worksheet.column_dimensions[column_letter].width = max_length + 2


async def farmers_to_excel(data: list):
    if not data:
        return None

    all_products = sorted(
        {
            (name or "-").strip() or "-"
            for farmer in data
            for name in (farmer.get("product_totals") or {}).keys()
        },
        key=lambda value: value.lower(),
    )

    formatted = []
    for index, farmer in enumerate(data, start=1):
        row = {
            "№": index,
            "Туман": farmer.get("district") or "-",
            "Массив": farmer.get("massive") or "-",
            "Фермер номи": farmer.get("name") or "-",
            "Шартнома миқдори (фақат фючерс)": _as_int_amount(farmer.get("futures_quantity")),
            "Шартнома суммаси": _as_int_amount(farmer.get("futures_amount")),
        }

        product_totals = farmer.get("product_totals") or {}
        for product_name in all_products:
            row[product_name] = _as_int_amount(product_totals.get(product_name))

        total_advance = float(farmer.get("farmer_total_amount") or 0)
        futures_amount = float(farmer.get("futures_amount") or 0)
        row["Жами"] = _as_int_amount(total_advance)
        row["Жами аванс шартноманинг % ташкил қилади"] = _as_percent(
            (total_advance / futures_amount * 100) if futures_amount > 0 else 0
        )
        row["Авансни қоплаш учун лозим бўлган пахта миқдори"] = _as_int_amount(total_advance / COTTON_PRICE)
        formatted.append(row)

    totals_row = {
        "№": "",
        "Туман": "",
        "Массив": "",
        "Фермер номи": "Жами",
        "Шартнома миқдори (фақат фючерс)": _as_int_amount(sum(float(farmer.get("futures_quantity") or 0) for farmer in data)),
        "Шартнома суммаси": _as_int_amount(sum(float(farmer.get("futures_amount") or 0) for farmer in data)),
    }
    for product_name in all_products:
        totals_row[product_name] = _as_int_amount(sum(float((farmer.get("product_totals") or {}).get(product_name) or 0) for farmer in data))
    grand_total_advance = sum(float(farmer.get("farmer_total_amount") or 0) for farmer in data)
    grand_total_futures_amount = sum(float(farmer.get("futures_amount") or 0) for farmer in data)
    totals_row["Жами"] = _as_int_amount(grand_total_advance)
    totals_row["Жами аванс шартноманинг % ташкил қилади"] = _as_percent(
        (grand_total_advance / grand_total_futures_amount * 100) if grand_total_futures_amount > 0 else 0
    )
    totals_row["Авансни қоплаш учун лозим бўлган пахта миқдори"] = _as_int_amount(grand_total_advance / COTTON_PRICE)
    formatted.append(totals_row)

    df = pd.DataFrame(formatted)
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Farmers")
        _autosize_and_bold(writer.sheets["Farmers"])

    buffer.seek(0)
    return buffer


CONTRACT_TYPE_LABELS = {
    "futures": "Фючерс",
    "forward": "Форвард",
    "storage": "Сақлаш",
    "all": "Ҳаммаси",
}


async def contracts_to_excel(data: list, contract_type: str = "all"):
    if not data:
        return None

    formatted = []
    for index, item in enumerate(data, start=1):
        row_contract_type = item.get("contract_type", contract_type)
        contract_type_label = CONTRACT_TYPE_LABELS.get(row_contract_type, "Ҳаммаси")
        formatted.append(
            {
                "№": index,
                "Шартнома тури": contract_type_label,
                "Вилоят": item["region"],
                "Туман": item["district"],
                "Массив": item["massive"],
                "Фермер": item["name"],
                "ИНН": item.get("inn") or "-",
                "Миқдор (тн)": float(item["quantity"]),
                "Сумма": float(item["amount"]),
            }
        )

    df = pd.DataFrame(formatted)
    buffer = BytesIO()

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Contracts")
        _autosize_and_bold(writer.sheets["Contracts"])

    buffer.seek(0)
    return buffer


async def warehouse_receipts_to_excel(data: list[dict]):
    if not data:
        return None

    formatted = []
    for index, item in enumerate(data, start=1):
        formatted.append(
            {
                "№": index,
                "Сана": _excel_date(item.get("date")),
                "Юк-хати №": item.get("invoice_number") or "-",
                "Маҳсулот": item.get("product_name") or "-",
                "Транспорт №": item.get("transport_number") or "-",
                "Қоп сони": item.get("bag_count") or 0,
                "Миқдори": float(item.get("quantity") or 0),
                "Омбор": item.get("warehouse_name") or "-",
            }
        )

    df = pd.DataFrame(formatted)
    buffer = BytesIO()

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="WarehouseReceipts")
        _autosize_and_bold(writer.sheets["WarehouseReceipts"])

    buffer.seek(0)
    return buffer


async def warehouse_expenses_to_excel(data: list[dict], mode: str = "out"):
    if not data:
        return None

    if mode == "out":
        data = sorted(
            data,
            key=lambda row: (
                row.get("district_name") or "-",
                row.get("massive_name") or "-",
                row.get("inn") or "-",
                row.get("farmer_name") or "-",
                row.get("number") or "-",
                row.get("product_name") or "-",
            ),
        )

    formatted = []
    for index, item in enumerate(data, start=1):
        if mode == "report":
            formatted.append(
                {
                    "№": index,
                    "Туман": item.get("district_name") or "-",
                    f"Бир кунда ({datetime.now().strftime('%d.%m.%Y')})": float(item.get("today_quantity") or 0),
                    "Миқдори (умумий)": float(item.get("total_quantity") or item.get("quantity") or 0),
                }
            )
            continue

        formatted.append(
            {
                "№": index,
                "Туман": item.get("district_name") or "-",
                "Массив": item.get("massive_name") or "-",
                "ИНН": item.get("inn") or "-",
                "Фермер номи": item.get("farmer_name") or "-",
                "Юк хати №": item.get("number") or "-",
                "Маҳсулот": item.get("product_name") or "-",
                "Нархи": float(item.get("price") or 0),
                "Миқдори": float(item.get("quantity") or 0),
                "НДС ставкаси": item.get("vat_rate") or "0",
                "Суммаси": float(item.get("amount") or 0),
                "НДС суммаси": float(item.get("vat_amount") or 0),
                "Жами сумма": float(item.get("total_with_vat") or 0),
            }
        )

    df = pd.DataFrame(formatted)
    buffer = BytesIO()

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="WarehouseExpenses")
        _autosize_and_bold(writer.sheets["WarehouseExpenses"])

    buffer.seek(0)
    return buffer
