from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile, InputMediaPhoto

_BG_COLOR = "#f4f7fb"
_CARD_COLOR = "#ffffff"
_HEADER_BG = "#1f6feb"
_HEADER_TEXT = "#ffffff"
_TITLE_COLOR = "#0b1f44"
_TEXT_COLOR = "#102a43"
_MUTED_TEXT = "#486581"
_BORDER = "#d9e2ec"
_ROW_ALT = "#f8fbff"
_BRAND_TEXT = "TETRATEX_bot"
_BRAND_LINK = "https://t.me/TETRATEX_bot"

_LOCAL_FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"


_BUNDLED_REGULAR_FONTS = [
    "ARIAL.TTF",
    "SEGOEUI.TTF",
    "SEGOEUIL.TTF",
    "SEGOEUII.TTF",
    "SEGOEUIZ.TTF",
    "SEGOEUISL.TTF",
    "SEGOESC.TTF",
    "SEGOEPR.TTF",
]

_BUNDLED_BOLD_FONTS = [
    "ARIALBD.TTF",
    "ARIBLK.TTF",
    "SEGOEUIB.TTF",
    "SEGUISB.TTF",
    "SEGOESCB.TTF",
    "SEGOEPRB.TTF",
]


_FONT_PATHS = [
    *(_LOCAL_FONTS_DIR / font_name for font_name in _BUNDLED_REGULAR_FONTS),
    _LOCAL_FONTS_DIR / "NotoSans-Regular.ttf",
    _LOCAL_FONTS_DIR / "DejaVuSans.ttf",
    "DejaVuSans.ttf",
    "NotoSans-Regular.ttf",
    "Arial.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]


def _load_font(size: int, bold: bool = False):
    from PIL import ImageFont

    pil_fonts_dir = Path(ImageFont.__file__).resolve().parent / "fonts"

    candidates = []
    if bold:
        candidates.extend(
            [
                *(_LOCAL_FONTS_DIR / font_name for font_name in _BUNDLED_BOLD_FONTS),
                _LOCAL_FONTS_DIR / "NotoSans-Bold.ttf",
                _LOCAL_FONTS_DIR / "DejaVuSans-Bold.ttf",
                pil_fonts_dir / "NotoSans-Bold.ttf",
                pil_fonts_dir / "DejaVuSans-Bold.ttf",
                "DejaVuSans-Bold.ttf",
                "NotoSans-Bold.ttf",
                "Arial Bold.ttf",
                "arialbd.ttf",
                "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
                "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
                "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
                "C:/Windows/Fonts/arialbd.ttf",
                "C:/Windows/Fonts/seguisb.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            ]
        )

    candidates.extend(
        [
            *(_LOCAL_FONTS_DIR / font_name for font_name in _BUNDLED_REGULAR_FONTS),
            pil_fonts_dir / "NotoSans-Regular.ttf",
            pil_fonts_dir / "DejaVuSans.ttf",
        ]
    )
    candidates.extend(_FONT_PATHS)

    for path in candidates:
        normalized_path = Path(path)
        if normalized_path.is_absolute() and not normalized_path.exists():
            continue
        try:
            return ImageFont.truetype(str(normalized_path), size)
        except OSError:
            continue

    return ImageFont.load_default()


def _text_size(draw, text: str, font) -> tuple[int, int]:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    return right - left, bottom - top


def _wrap_text_to_width(draw, text: str, font, max_width: int) -> list[str]:
    if max_width <= 0:
        return [text]

    wrapped_lines: list[str] = []
    for raw_line in str(text).splitlines() or [""]:
        words = raw_line.split()
        if not words:
            wrapped_lines.append("")
            continue

        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            candidate_w, _ = _text_size(draw, candidate, font)
            if candidate_w <= max_width:
                current = candidate
                continue
            wrapped_lines.append(current)
            current = word
        wrapped_lines.append(current)

    return wrapped_lines or [str(text)]


def _draw_multiline_text(
    draw,
    lines: list[str],
    *,
    x: float,
    y: float,
    font,
    fill: str,
    line_gap: int = 4,
    align: str = "left",
    box_width: int | None = None,
) -> None:
    current_y = y
    for line in lines:
        line_x = x
        if align == "center" and box_width is not None:
            line_width, _ = _text_size(draw, line, font)
            line_x = x + (box_width - line_width) / 2
        draw.text((line_x, current_y), line, font=font, fill=fill)
        current_y += _text_size(draw, line or "Ag", font)[1] + line_gap


def _fit_font_to_width(draw, text: str, *, target_width: int, max_size: int = 30, min_size: int = 10):
    for size in range(max_size, min_size - 1, -1):
        font = _load_font(size, bold=True)
        width, _ = _text_size(draw, text, font)
        if width <= target_width:
            return font
    return _load_font(min_size, bold=True)


def _parse_cell(cell: Any) -> tuple[str, str | None]:
    if isinstance(cell, tuple) and len(cell) == 2:
        return str(cell[0]), str(cell[1])
    return str(cell), None


def _build_qr_image(size: int):
    from PIL import Image, ImageDraw

    try:
        import qrcode

        qr = qrcode.QRCode(border=1, box_size=10)
        qr.add_data(_BRAND_LINK)
        qr.make(fit=True)
        return qr.make_image(fill_color="black", back_color="white").convert("RGB").resize((size, size), Image.Resampling.NEAREST)
    except ImportError:
        fallback = Image.new("RGB", (size, size), "white")
        fallback_draw = ImageDraw.Draw(fallback)
        cell = max(4, size // 21)

        def square(x0: int, y0: int, cells: int):
            fallback_draw.rectangle((x0, y0, x0 + cells * cell, y0 + cells * cell), outline="black", width=cell)
            fallback_draw.rectangle(
                (x0 + 2 * cell, y0 + 2 * cell, x0 + (cells - 2) * cell, y0 + (cells - 2) * cell),
                fill="black",
            )

        square(cell, cell, 7)
        square(size - 8 * cell, cell, 7)
        square(cell, size - 8 * cell, 7)

        for y in range(10, 19, 2):
            for x in range(10, 19, 2):
                fallback_draw.rectangle((x * cell, y * cell, x * cell + cell, y * cell + cell), fill="black")

        return fallback


def _draw_branding(img, draw, *, side_padding: int, top_pad: int, image_width: int) -> None:
    qr_size = 92
    brand_font = _fit_font_to_width(draw, _BRAND_TEXT, target_width=qr_size, max_size=30, min_size=10)
    text_w, text_h = _text_size(draw, _BRAND_TEXT, brand_font)
    box_padding_x = 16
    box_padding_y = 10
    gap = 8

    badge_w = box_padding_x * 2 + qr_size
    badge_h = box_padding_y * 2 + qr_size + gap + text_h
    badge_x = image_width - side_padding - badge_w
    badge_y = top_pad

    draw.rounded_rectangle(
        (badge_x, badge_y, badge_x + badge_w, badge_y + badge_h),
        radius=14,
        fill="#ffffff",
        outline=_BORDER,
        width=2,
    )

    qr_image = _build_qr_image(qr_size)
    qr_x = badge_x + (badge_w - qr_size) // 2
    qr_y = badge_y + box_padding_y
    img.paste(qr_image, (qr_x, qr_y))

    text_x = badge_x + (badge_w - text_w) / 2
    text_y = qr_y + qr_size + gap
    draw.text((text_x, text_y), _BRAND_TEXT, font=brand_font, fill=_TITLE_COLOR)


def _branding_badge_height(draw) -> int:
    qr_size = 92
    brand_font = _fit_font_to_width(draw, _BRAND_TEXT, target_width=qr_size, max_size=30, min_size=10)
    _, text_h = _text_size(draw, _BRAND_TEXT, brand_font)
    box_padding_y = 10
    gap = 8
    return box_padding_y * 2 + qr_size + gap + text_h


def build_table_image(
    *,
    title: str,
    columns: list[str],
    rows: list[list[Any]],
    header_groups: list[dict[str, Any]] | None = None,
    row_span_columns: int = 0,
    subtitle: str | None = None,
    subtitle_alignment: str = "left",
    top_note: str | None = None,
    top_note_alignment: str = "left",
    top_note_color: str = _MUTED_TEXT,
    top_note_right_padding: int | None = None,
    subtitle_bold: bool = False,
    subtitle_color: str = _MUTED_TEXT,
    top_note_bold: bool = False,
    footer_lines: list[str] | None = None,
    equal_column_width: bool = False,
    column_width: int | None = None,
    column_widths: list[int] | None = None,
    column_alignments: list[str] | None = None,
    min_rows: int | None = None,
) -> bytes:
    from PIL import Image, ImageDraw

    title_font = _load_font(34, bold=True)
    subtitle_font = _load_font(22, bold=subtitle_bold)
    header_font = _load_font(23, bold=True)
    body_font = _load_font(22)
    body_bold_font = _load_font(22, bold=True)
    footer_font = _load_font(21, bold=True)
    top_note_font = _load_font(22, bold=top_note_bold)

    tmp = Image.new("RGB", (10, 10), _BG_COLOR)
    draw = ImageDraw.Draw(tmp)

    col_widths: list[int] = []
    for col_index, col in enumerate(columns):
        max_width, _ = _text_size(draw, col, header_font)
        for row in rows:
            cell = row[col_index] if col_index < len(row) else ""
            cell_text, _ = _parse_cell(cell)
            cell_width, _ = _text_size(draw, cell_text, body_font)
            max_width = max(max_width, cell_width)
        col_widths.append(max_width + 34)

    if column_widths:
        if len(column_widths) != len(columns):
            raise ValueError("column_widths length must match columns length")
        col_widths = [max(1, width) for width in column_widths]
    elif equal_column_width and col_widths:
        enforced_width = max(col_widths)
        if column_width is not None:
            enforced_width = max(enforced_width, column_width)
        col_widths = [enforced_width] * len(col_widths)

    if column_alignments and len(column_alignments) != len(columns):
        raise ValueError("column_alignments length must match columns length")

    alignments = [
        (column_alignments[idx].lower() if column_alignments else "left")
        for idx in range(len(columns))
    ]

    for alignment in alignments:
        if alignment not in {"left", "center", "right"}:
            raise ValueError("column_alignments must be left, center or right")

    side_padding = 34
    cell_padding_y = 18
    table_width = sum(col_widths)
    image_width = max(900, table_width + side_padding * 2)

    title_h = _text_size(draw, title, title_font)[1]
    subtitle_alignment = subtitle_alignment.lower()
    if subtitle_alignment not in {"left", "center", "right"}:
        raise ValueError("subtitle_alignment must be left, center or right")

    subtitle_lines = subtitle.splitlines() if subtitle else []
    subtitle_line_h = _text_size(draw, "Ag", subtitle_font)[1] if subtitle else 0
    subtitle_line_gap = 12
    title_block_gap = 12
    subtitle_h = (
        len(subtitle_lines) * subtitle_line_h + (len(subtitle_lines) - 1) * subtitle_line_gap
        if subtitle_lines
        else 0
    )
    top_note_h = _text_size(draw, top_note or "", top_note_font)[1] if top_note else 0

    top_note_alignment = top_note_alignment.lower()
    if top_note_alignment not in {"left", "center", "right"}:
        raise ValueError("top_note_alignment must be left, center or right")
    has_grouped_header = bool(header_groups)
    header_line_h = _text_size(draw, "Ag", header_font)[1]
    header_line_gap = 4

    wrapped_column_headers = [
        _wrap_text_to_width(draw, col, header_font, max(1, col_widths[idx] - 32))
        for idx, col in enumerate(columns)
    ]
    row_span_column_count = min(max(0, row_span_columns), len(columns))

    if has_grouped_header:
        wrapped_group_titles = []
        group_start_idx_for_wrap = row_span_column_count
        for group in header_groups or []:
            span = int(group.get("span") or 0)
            group_width = sum(col_widths[group_start_idx_for_wrap:group_start_idx_for_wrap + max(0, span)])
            wrapped_group_titles.append(
                _wrap_text_to_width(draw, str(group.get("title") or ""), header_font, max(1, group_width - 32))
            )
            group_start_idx_for_wrap += max(0, span)

        top_header_lines = max([1, *[len(lines) for lines in wrapped_group_titles]])
        bottom_header_lines = max(
            [
                1,
                *[len(wrapped_column_headers[idx]) for idx in range(row_span_column_count, len(columns))],
            ]
        )
        header_top_h = top_header_lines * header_line_h + max(0, top_header_lines - 1) * header_line_gap + cell_padding_y * 2
        header_bottom_h = bottom_header_lines * header_line_h + max(0, bottom_header_lines - 1) * header_line_gap + cell_padding_y * 2
        header_h = header_top_h + header_bottom_h
    else:
        header_lines = max([1, *[len(lines) for lines in wrapped_column_headers]])
        header_h = header_lines * header_line_h + max(0, header_lines - 1) * header_line_gap + cell_padding_y * 2
        header_top_h = header_h
        header_bottom_h = 0

    row_h = _text_size(draw, "Ag", body_font)[1] + cell_padding_y * 2
    footer_h = (_text_size(draw, "Ag", footer_font)[1] + 12) * len(footer_lines or [])

    top_pad = 28
    text_gap = 18
    table_top = (
        top_pad
        + title_h
        + (subtitle_h + title_block_gap if subtitle else 0)
        + (top_note_h + title_block_gap if top_note else 0)
        + text_gap
    )

    # Reserve space for the QR branding badge so it cannot overlap the table header.
    branding_bottom = top_pad + _branding_badge_height(draw) + text_gap
    table_top = max(table_top, branding_bottom)
    row_count = max(1, len(rows), min_rows or 0)
    table_h = header_h + row_count * row_h
    image_height = table_top + table_h + footer_h + 44

    img = Image.new("RGBA", (image_width, image_height), _BG_COLOR)
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle((12, 12, image_width - 12, image_height - 12), radius=18, fill=_CARD_COLOR, outline=_BORDER, width=2)
    _draw_branding(img, draw, side_padding=side_padding, top_pad=top_pad, image_width=image_width)

    draw.text((side_padding, top_pad), title, font=title_font, fill=_TITLE_COLOR)
    subtitle_y = top_pad + title_h + title_block_gap
    if subtitle_lines:
        current_subtitle_y = subtitle_y
        for subtitle_line in subtitle_lines:
            line_w, _ = _text_size(draw, subtitle_line, subtitle_font)
            if subtitle_alignment == "center":
                subtitle_x = (image_width - line_w) / 2
            elif subtitle_alignment == "right":
                subtitle_x = image_width - side_padding - line_w
            else:
                subtitle_x = side_padding
            draw.text((subtitle_x, current_subtitle_y), subtitle_line, font=subtitle_font, fill=subtitle_color)
            current_subtitle_y += subtitle_line_h + subtitle_line_gap

    if top_note:
        top_note_y = subtitle_y + (subtitle_h + title_block_gap if subtitle else 0)
        top_note_w, _ = _text_size(draw, top_note, top_note_font)
        right_padding = side_padding if top_note_right_padding is None else max(0, top_note_right_padding)
        if top_note_alignment == "right":
            top_note_x = image_width - right_padding - top_note_w
        elif top_note_alignment == "center":
            top_note_x = (image_width - top_note_w) / 2
        else:
            top_note_x = side_padding
        draw.text((top_note_x, top_note_y), top_note, font=top_note_font, fill=top_note_color)

    x = side_padding
    y = table_top
    draw.rounded_rectangle((x, y, x + table_width, y + header_h), radius=12, fill=_HEADER_BG)

    cursor_x = x
    if has_grouped_header:
        split_y = y + header_top_h
        split_start_x = x + sum(col_widths[:max(0, row_span_columns)])
        if split_start_x < x + table_width:
            draw.line((split_start_x, split_y, x + table_width, split_y), fill=_BORDER, width=1)

        cumulative_widths = [x]
        for width in col_widths:
            cumulative_widths.append(cumulative_widths[-1] + width)

        for idx in range(1, len(columns)):
            line_top = y if idx <= row_span_columns else split_y
            draw.line((cumulative_widths[idx], line_top, cumulative_widths[idx], y + table_h), fill=_BORDER, width=1)

        group_boundary_idx = row_span_columns
        for group in header_groups or []:
            group_boundary_idx += int(group.get("span") or 0)
            if group_boundary_idx >= len(columns):
                continue
            draw.line((cumulative_widths[group_boundary_idx], y, cumulative_widths[group_boundary_idx], y + table_h), fill=_BORDER, width=1)

        cursor_x = x
        for idx in range(min(row_span_columns, len(columns))):
            wrapped_lines = wrapped_column_headers[idx]
            text_block_h = len(wrapped_lines) * header_line_h + max(0, len(wrapped_lines) - 1) * header_line_gap
            text_y = y + (header_h - text_block_h) / 2
            _draw_multiline_text(
                draw,
                wrapped_lines,
                x=cursor_x,
                y=text_y,
                font=header_font,
                fill=_HEADER_TEXT,
                line_gap=header_line_gap,
                align="center",
                box_width=col_widths[idx],
            )
            cursor_x += col_widths[idx]

        group_start_idx = row_span_columns
        cursor_x = x + sum(col_widths[:row_span_columns])
        for group_idx, group in enumerate(header_groups or []):
            span = int(group.get("span") or 0)
            if span <= 0:
                continue
            group_width = sum(col_widths[group_start_idx:group_start_idx + span])
            wrapped_title_lines = wrapped_group_titles[group_idx]
            title_block_h = len(wrapped_title_lines) * header_line_h + max(0, len(wrapped_title_lines) - 1) * header_line_gap
            _draw_multiline_text(
                draw,
                wrapped_title_lines,
                x=cursor_x,
                y=y + (header_top_h - title_block_h) / 2,
                font=header_font,
                fill=_HEADER_TEXT,
                line_gap=header_line_gap,
                align="center",
                box_width=group_width,
            )
            cursor_x += group_width
            group_start_idx += span

        cursor_x = x + sum(col_widths[:row_span_columns])
        for idx in range(row_span_columns, len(columns)):
            wrapped_lines = wrapped_column_headers[idx]
            text_block_h = len(wrapped_lines) * header_line_h + max(0, len(wrapped_lines) - 1) * header_line_gap

            _draw_multiline_text(
                draw,
                wrapped_lines,
                x=cursor_x,
                y=y + header_top_h + (header_bottom_h - text_block_h) / 2,
                font=header_font,
                fill=_HEADER_TEXT,
                line_gap=header_line_gap,
                align="center",
                box_width=col_widths[idx],
            )
            cursor_x += col_widths[idx]
    else:
        for idx in range(len(columns)):
            wrapped_lines = wrapped_column_headers[idx]
            text_block_h = len(wrapped_lines) * header_line_h + max(0, len(wrapped_lines) - 1) * header_line_gap

            _draw_multiline_text(
                draw,
                wrapped_lines,
                x=cursor_x,
                y=y + (header_h - text_block_h) / 2,
                font=header_font,
                fill=_HEADER_TEXT,
                line_gap=header_line_gap,
                align="center",
                box_width=col_widths[idx],
            )
            if idx > 0:
                draw.line((cursor_x, y, cursor_x, y + table_h), fill=_BORDER, width=1)
            cursor_x += col_widths[idx]

    y += header_h
    if rows:
        padded_rows = rows
        if min_rows and len(rows) < min_rows:
            padded_rows = rows + [["" for _ in columns] for _ in range(min_rows - len(rows))]

        for row_idx, row in enumerate(padded_rows):
            row_bg = _ROW_ALT if row_idx % 2 == 0 else _CARD_COLOR
            draw.rectangle((x, y, x + table_width, y + row_h), fill=row_bg)
            is_total_row = any((str(cell).strip().upper() == "ЖАМИ") for cell in row)
            row_font = body_bold_font if is_total_row else body_font
            cursor_x = x
            for col_idx, width in enumerate(col_widths):
                cell = row[col_idx] if col_idx < len(row) else ""
                cell_text, cell_color = _parse_cell(cell)
                cell_w, _ = _text_size(draw, cell_text, row_font)
                if alignments[col_idx] == "center":
                    text_x = cursor_x + (width - cell_w) / 2
                elif alignments[col_idx] == "right":
                    text_x = cursor_x + width - cell_w - 16
                else:
                    text_x = cursor_x + 16

                draw.text((text_x, y + cell_padding_y), cell_text, font=row_font, fill=cell_color or _TEXT_COLOR)
                cursor_x += width
            draw.line((x, y + row_h, x + table_width, y + row_h), fill=_BORDER, width=1)
            y += row_h
    else:
        draw.rectangle((x, y, x + table_width, y + row_h), fill=_CARD_COLOR)
        draw.text((x + 16, y + cell_padding_y), "Маълумот йўқ", font=body_font, fill=_MUTED_TEXT)
        draw.line((x, y + row_h, x + table_width, y + row_h), fill=_BORDER, width=1)
        y += row_h

    if footer_lines:
        y += 14
        for line in footer_lines:
            draw.text((side_padding, y), line, font=footer_font, fill=_TITLE_COLOR)
            y += _text_size(draw, line, footer_font)[1] + 12

    buf = BytesIO()
    img.convert("RGB").save(buf, format="PNG", optimize=True)
    return buf.getvalue()


async def send_or_edit_table_image(target, image_bytes: bytes, keyboard, edit: bool):
    file = BufferedInputFile(image_bytes, filename="table.png")

    if edit:
        try:
            await target.edit_media(media=InputMediaPhoto(media=file), reply_markup=keyboard)
            return
        except TelegramBadRequest:
            pass

    await target.answer_photo(photo=file, reply_markup=keyboard)
    if edit:
        try:
            await target.delete()
        except TelegramBadRequest:
            pass
