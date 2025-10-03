#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
from typing import List, Optional
from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import RectangleObject
from pypdf import PageObject


class PaperSize:
    """页面尺寸（pt）1 pt = 1/72 inch"""
    # A4: 210mm x 297mm
    A4 = RectangleObject([0, 0, 595.276, 841.890])
    # A3: 297mm x 420mm
    A3 = RectangleObject([0, 0, 841.890, 1190.551])


def normalize_to_a4(page: PageObject) -> PageObject:
    """
    将任意大小的 page 规范化为 A4：
    - 比 A4 大：不缩放，居中放置到 A4 画布上，超出部分被 A4 裁切掉
    - 比 A4 小：不缩放，居中放置到 A4 画布上（四周留白）
    """
    a4w, a4h = float(PaperSize.A4.width), float(PaperSize.A4.height)
    pw, ph = float(page.mediabox.width), float(page.mediabox.height)

    dst = PageObject.create_blank_page(width=a4w, height=a4h)

    dx = (a4w - pw) / 2.0
    dy = (a4h - ph) / 2.0
    t = Transformation().translate(dx, dy)

    # 把原页“绘制”到 A4；超出 A4 的部分被裁掉
    dst.merge_transformed_page(page, t)
    return dst


def compute_groups(total_pages: int, user_booklet_pages: Optional[int]) -> List[int]:
    """
    分组逻辑：
    - 若用户指定每册页数（必须为 4 的倍数），就按该大小分组
    - 否则：总页数 <= 20 则一次性补齐到 4 的倍数
             否则按 20 一组，末组补齐到 4 的倍数
    """
    if user_booklet_pages is not None:
        if user_booklet_pages % 4 != 0:
            raise ValueError("Number of booklet pages must be a multiple of 4")
        # 注意：为了覆盖全部页，最后一组可能不满，仍按指定册数补齐
        num_groups = (total_pages + user_booklet_pages - 1) // user_booklet_pages
        return [user_booklet_pages] * num_groups

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


def add_booklet(writer: PdfWriter,
                a4_pages: List[PageObject],
                anti_bleed_inch: float = 0.14) -> None:
    """
    将 A4 页列表拼成 A3 横向对折小册子，并整体“放大一点”，抵消打印出血。
    - a4_pages: 已经规范为 A4 的页面（数量必须为 4 的倍数）
    - anti_bleed_inch: 期望抵消的“出血”宽度（英寸）。例如 Okular 默认 0.14 inch。
      原理：把整张 A3 画布内容按比例放大到可覆盖上下左右各 anti_bleed 的额外区域，
           然后整体向外平移（负方向），让内容“伸出页面边界”进入出血区。
    """
    num_pages = len(a4_pages)
    assert num_pages % 4 == 0, "booklet 组的页数必须是 4 的倍数"

    A4W = float(PaperSize.A4.width)
    A4H = float(PaperSize.A4.height)

    # A3 横向尺寸：宽= A3 高；高= A3 宽
    A3W = float(PaperSize.A3.height)   # 1190.551
    A3H = float(PaperSize.A3.width)    # 841.890

    LEFT_ORIGIN = (0.0, 0.0)     # 左页左下角
    RIGHT_ORIGIN = (A4W, 0.0)    # 右页左下角

    bleed_pt = anti_bleed_inch * 72.0

    # 计算“放大比例”：
    # 想要内容覆盖 [0 - bleed_pt, W + bleed_pt] × [0 - bleed_pt, H + bleed_pt]
    # 令缩放后有效尺寸为 s*W、s*H，并整体平移 (-bleed_pt, -bleed_pt)
    # s_x 需满足：s*W >= W + 2*bleed_pt => s >= 1 + 2*bleed_pt/W
    # s_y 同理；为保持等比，取 s = max(s_x, s_y)
    sx = 1.0 + (2.0 * bleed_pt / A3W)
    sy = 1.0 + (2.0 * bleed_pt / A3H)
    s = max(sx, sy)

    # 放大后，把原点平移到 (-bleed_pt, -bleed_pt)，保证四边都溢出到出血区
    # 注意 pypdf 的组合变换是“先做前面的，后做后面的”，所以我们做：
    # scale(s) -> translate(-bleed_pt, -bleed_pt)
    # 结果是：x' = s*x - bleed_pt, y' = s*y - bleed_pt
    post_scale_translate = Transformation().scale(s).translate(-bleed_pt, -bleed_pt)

    for i in range(num_pages // 2):
        # 先在“基底”A3 页上按原始未放大尺寸摆好左右两页
        base = PageObject.create_blank_page(width=A3W, height=A3H)

        if i % 2 == 0:
            left_page = a4_pages[num_pages - 1 - i]
            right_page = a4_pages[i]
        else:
            left_page = a4_pages[i]
            right_page = a4_pages[num_pages - 1 - i]

        base.merge_transformed_page(left_page,  Transformation().translate(*LEFT_ORIGIN))
        base.merge_transformed_page(right_page, Transformation().translate(*RIGHT_ORIGIN))

        # 真正写入的 A3 页面：把“基底”整体放大，并负向平移以占满出血区
        canvas = writer.add_blank_page(width=A3W, height=A3H)
        canvas.merge_transformed_page(base, post_scale_translate)


def parse_args(argv: List[str]):
    """
    简单参数解析：
    - argv[1]: 输入 PDF 路径（必填）
    - 可选：一个纯数字，表示每册页数（必须是 4 的倍数）
    - 可选：--anti-bleed=<inches> 例如 --anti-bleed=0.14
    """
    if len(argv) < 2:
        print("Usage: python booklet.py <input.pdf> [booklet_pages] [--anti-bleed=0.14]")
        sys.exit(1)

    filename = argv[1]
    booklet_pages: Optional[int] = None
    anti_bleed_inch: float = 0.14

    for a in argv[2:]:
        if a.startswith("--anti-bleed="):
            try:
                anti_bleed_inch = float(a.split("=", 1)[1])
            except Exception:
                pass
        elif a.isdigit():
            booklet_pages = int(a)

    return filename, booklet_pages, anti_bleed_inch


def main():
    filename, booklet_pages, anti_bleed_inch = parse_args(sys.argv)

    reader = PdfReader(filename)
    total_pages = len(reader.pages)

    # 1) 先把所有页面规范化为 A4
    normalized_a4_pages: List[PageObject] = [normalize_to_a4(p) for p in reader.pages]

    # 2) 放入“扩展器”，便于后续分组补空白页
    extender = PdfWriter()
    for p in normalized_a4_pages:
        extender.add_page(p)

    # 3) 计算分组，并在每组末尾补足到 4 的倍数（空白 A4）
    groups = compute_groups(total_pages, booklet_pages)
    a4w, a4h = float(PaperSize.A4.width), float(PaperSize.A4.height)

    page_cursor = 0
    for gsize in groups:
        have = len(extender.pages) - page_cursor
        while have < gsize:
            extender.add_blank_page(width=a4w, height=a4h)
            have += 1
        page_cursor += gsize

    # 4) 逐组拼成 A3 横向对折小册子，并对整张 A3 画面做“放大+负向平移”以抵消出血
    writer = PdfWriter()
    cursor = 0
    for gsize in groups:
        group_slice = [extender.pages[i] for i in range(cursor, cursor + gsize)]
        add_booklet(writer, group_slice, anti_bleed_inch=anti_bleed_inch)
        cursor += gsize

    # 5) 输出文件
    base, ext = os.path.splitext(filename)
    outname = f"{base}-booklet.pdf"
    with open(outname, "wb") as fp:
        writer.write(fp)
    print(f"输出完成: {outname}")


if __name__ == "__main__":
    main()
