from typing import Sequence


def paginate_data(data: Sequence, page: int, per_page: int):
    start = (page - 1) * per_page
    end = start + per_page
    return data[start:end], start, end


def build_page_text(title: str, headers: str, rows: list[str], subheaders: str | None = None):
    text = f"{title}\n\n{headers}\n"
    if subheaders:
        text += f"{subheaders}\n"
    text += "-" * 37 + "\n"

    if rows:
        text += "\n".join(rows) + "\n"

    return text
