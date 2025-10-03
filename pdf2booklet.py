#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import RectangleObject
from pypdf import PageObject


class PaperSize:
    # 1 pt = 1/72 inch；A4/A3 尺寸（pt）
    A4 = RectangleObject([0, 0, 595.276, 841.890])     # 210mm x 297mm
    A3 = RectangleObject([0, 0, 841.890, 1190.551])    # 297mm x 420mm


def normalize_to_a4(page: PageObject) -> PageObject:
    """
    将任意大小的 page 规范化为 A4：
    - 比 A4 大：不缩放，居中放置到 A4 画布上，超出部分被 A4 裁切掉
    - 比 A4 小：不缩放，居中放置到 A4 画布上（四周留白）
    """
    a4w, a4h = float(PaperSize.A4.width), float(PaperSize.A4.height)
    pw, ph = float(page.mediabox.width), float(page.mediabox.height)

    # 目标：A4 空白页
    dst = PageObject.create_blank_page(width=a4w, height=a4h)

    # 将原页中心对齐到 A4 中心（仅平移，不缩放）
    dx = (a4w - pw) / 2.0
    dy = (a4h - ph) / 2.0
    t = Transformation().translate(dx, dy)

    # 把带有平移的原页“画”到 A4 上；超出 A4 的部分自然被裁掉
    dst.merge_transformed_page(page, t)
    return dst


def add_booklet(writer: PdfWriter, a4_pages: list[PageObject]) -> None:
    """
    假设传入的 pages 已经全部是 A4 尺寸，拼成 A3 横向对折的小册子。
    页面对： (N-1, 0), (1, N-2), (N-3, 2), ...
    偶数计数位在左，奇数计数位在右；默认从外到内对折顺序。
    """
    num_pages = len(a4_pages)
    assert num_pages % 4 == 0, "booklet 组的页数必须是 4 的倍数"

    a4w, a4h = float(PaperSize.A4.width), float(PaperSize.A4.height)
    # A3 横向：宽 = A3 高， 高 = A3 宽（pypdf 坐标系以 pt 为单位）
    A3_LANDSCAPE_W = float(PaperSize.A3.height)  # 1190.551
    A3_LANDSCAPE_H = float(PaperSize.A3.width)   # 841.890

    # 左右页的左下角放置点（左页 x=0，右页 x=a4w；都贴底 y=0）
    left_origin = (0.0, 0.0)
    right_origin = (a4w, 0.0)

    # 依次拼 2 页到 1 个 A3 横向页面
    for i in range(num_pages // 2):
        # 新建一张 A3 横向空白页
        canvas = writer.add_blank_page(width=A3_LANDSCAPE_W, height=A3_LANDSCAPE_H)

        # 计算这一对的左右页（经典小册子对折顺序）
        if i % 2 == 0:
            left_page = a4_pages[num_pages - 1 - i]
            right_page = a4_pages[i]
        else:
            left_page = a4_pages[i]
            right_page = a4_pages[num_pages - 1 - i]

        # 左页放到 (0, 0)
        canvas.merge_transformed_page(left_page, Transformation().translate(*left_origin))
        # 右页放到 (a4w, 0)
        canvas.merge_transformed_page(right_page, Transformation().translate(*right_origin))


def compute_groups(total_pages: int, user_booklet_pages: int | None) -> list[int]:
    """
    复用你的分组逻辑：优先用用户指定，否则 20 页为一组，末组补齐到 4 的倍数；
    若总页数 <= 20，则一次性补齐到 4 的倍数。
    """
    if user_booklet_pages is not None:
        if user_booklet_pages % 4 != 0:
            raise ValueError("Number of booklet pages must be a multiple of 4")
        return [user_booklet_pages] * ((total_pages + user_booklet_pages - 1) // user_booklet_pages)

    if total_pages <= 20:
        group_size = ((total_pages + 3) // 4) * 4
        return [group_size]

    num_full_groups = total_pages // 20
    remainder = total_pages % 20
    groups = [20] * num_full_groups
    if remainder > 0:
        last_group_size = ((remainder + 3) // 4) * 4
        groups.append(last_group_size)
    return groups


def main():
    if len(sys.argv) < 2:
        print("Usage: python booklet.py <input.pdf> [booklet_pages]")
        sys.exit(1)

    filename = sys.argv[1]
    user_booklet_pages = int(sys.argv[2]) if len(sys.argv) > 2 else None

    reader = PdfReader(filename)
    total_pages = len(reader.pages)

    # 先把所有页“规范化为 A4”（裁切或垫白）
    normalized_a4_pages: list[PageObject] = []
    for p in reader.pages:
        normalized_a4_pages.append(normalize_to_a4(p))

    # 复制到一个“扩展器”，方便后续按组补齐空白页
    extender = PdfWriter()
    for p in normalized_a4_pages:
        extender.add_page(p)

    # 分组并补齐到 4 的倍数（用空白 A4 垫页）
    group_sizes = compute_groups(total_pages, user_booklet_pages)
    a4w, a4h = float(PaperSize.A4.width), float(PaperSize.A4.height)

    page_cursor = 0
    for gsize in group_sizes:
        # 当前组已有多少页
        have = len(extender.pages) - page_cursor
        # 该组内不足的部分补空白 A4
        while have < gsize:
            extender.add_blank_page(width=a4w, height=a4h)
            have += 1
        page_cursor += gsize

    # 把各组做成 booklet
    writer = PdfWriter()
    cursor = 0
    for gsize in group_sizes:
        group_slice = [extender.pages[i] for i in range(cursor, cursor + gsize)]
        add_booklet(writer, group_slice)
        cursor += gsize

    base, ext = os.path.splitext(filename)
    outname = f"{base}-booklet.pdf"
    with open(outname, "wb") as fp:
        writer.write(fp)
    print(f"输出完成: {outname}")


if __name__ == "__main__":
    main()
