#11111111111111111111111111
from io import BytesIO
import pandas as pd
from openpyxl.styles import Font


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

    formatted = []
    for index, farmer in enumerate(data, start=1):
        formatted.append(
            {
                "№": index,
                "ИНН": farmer["inn"],
                "Фермер номи": farmer["name"],
                "Баланс": float(farmer["balance"]),
            }
        )

    df = pd.DataFrame(formatted)
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Farmers")
        _autosize_and_bold(writer.sheets["Farmers"])

    buffer.seek(0)
    return buffer


async def contracts_to_excel(data: list):
    if not data:
        return None

    formatted = []
    for index, item in enumerate(data, start=1):
        formatted.append(
            {
                "№": index,
                "Вилоят": item["region"],
                "Туман": item["district"],
                "Массив": item["massive"],
                "Фермер": item["name"],
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
                "Сана": item.get("date"),
                "Накладной": item.get("invoice_number") or "-",
                "Маҳсулот": item.get("product_name") or "-",
                "Қоп сони": item.get("bag_count") or 0,
                "Миқдор": float(item.get("quantity") or 0),
            }
        )

    df = pd.DataFrame(formatted)
    buffer = BytesIO()

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="WarehouseReceipts")
        _autosize_and_bold(writer.sheets["WarehouseReceipts"])

    buffer.seek(0)
    return buffer


async def warehouse_expenses_to_excel(data: list[dict]):
    if not data:
        return None

    formatted = []
    for index, item in enumerate(data, start=1):
        formatted.append(
            {
                "№": index,
                "Сана": item.get("date") or "-",
                "Ҳужжат №": item.get("number") or item.get("invoice_number") or "-",
                "Фермер": item.get("farmer_name") or item.get("district_name") or "-",
                "Маҳсулот": item.get("product_name") or "-",
                "Миқдор": float(item.get("quantity") or 0),
                "Га/кг": round(float(item.get("quantity_per_area") or 0)),
            }
        )

    df = pd.DataFrame(formatted)
    buffer = BytesIO()

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="WarehouseExpenses")
        _autosize_and_bold(writer.sheets["WarehouseExpenses"])

    buffer.seek(0)
    return buffer
