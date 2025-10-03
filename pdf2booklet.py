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
    将任意大小/坐标系/旋转的 page 规范化为 A4：
    - 尊重原始 mediabox 的 left/bottom 偏移
    - 应用 /Rotate（90/180/270）后再做几何对齐
    - 不缩放：大于 A4 的部分被裁切（中心裁切）；小于 A4 则居中垫白
    """
    a4w, a4h = float(PaperSize.A4.width), float(PaperSize.A4.height)

    mb = page.mediabox
    llx, lly = float(mb.left), float(mb.bottom)
    pw, ph   = float(mb.width), float(mb.height)

    # 取 /Rotate；pypdf 通常提供 page.rotation（可能为 None）
    rot = getattr(page, "rotation", 0) or 0
    rot = int(rot) % 360
    if rot not in (0, 90, 180, 270):
        # 非 90 的倍数基本很少见，这里保守归零
        rot = 0

    # 旋转后的“可视宽高”
    if rot in (0, 180):
        rw, rh = pw, ph
    else:
        rw, rh = ph, pw

    # 目标：A4 空白画布
    dst = PageObject.create_blank_page(width=a4w, height=a4h)

    # 基础：把原页面移到 (0,0)（消除 mediabox 偏移）
    T = Transformation().translate(-llx, -lly)

    # 应用 /Rotate，并把旋转后的内容“复位”到左下为 (0,0)（保证后续居中位移可用）
    if rot == 90:
        # (x,y)->(-y,x), bounds: x'∈[-ph,0], y'∈[0,pw] => 平移 (ph, 0)
        T = T.rotate(90).translate(ph, 0)
    elif rot == 180:
        # (x,y)->(-x,-y), bounds: x'∈[-pw,0], y'∈[-ph,0] => 平移 (pw, ph)
        T = T.rotate(180).translate(pw, ph)
    elif rot == 270:
        # (x,y)->(y,-x), bounds: x'∈[0,ph], y'∈[-pw,0] => 平移 (0, pw)
        T = T.rotate(270).translate(0, pw)
    # rot == 0: 不动

    # 现在旋转/复位后，内容左下角就是 (0,0)，尺寸 (rw, rh)
    # 居中放到 A4：中心对中心（真正对称）
    dx = (a4w - rw) / 2.0
    dy = (a4h - rh) / 2.0
    T = T.translate(dx, dy)

    # 把经过上述几何处理的原页“绘制”到 A4；超出 A4 的部分自然被裁掉
    dst.merge_transformed_page(page, T)
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
                a4_pages: list[PageObject],
                anti_bleed_inch: float = 0.14) -> None:
    """
    将 A4 页列表拼成 A3 横向对折小册子，并“绕页面中心”放大，来对称抵消打印出血。
    """
    num_pages = len(a4_pages)
    assert num_pages % 4 == 0, "booklet 组的页数必须是 4 的倍数"

    A4W = float(PaperSize.A4.width)
    A3W = float(PaperSize.A3.height)   # 横向宽
    A3H = float(PaperSize.A3.width)    # 横向高

    LEFT_ORIGIN  = (0.0, 0.0)
    RIGHT_ORIGIN = (A4W, 0.0)

    bleed_pt = anti_bleed_inch * 72.0

    # 目标：放大后，内容比 A3 四边各多出 bleed_pt
    # s_x = 1 + 2*bleed/A3W, s_y = 1 + 2*bleed/A3H，取等比 s=max(...)
    sx = 1.0 + (2.0 * bleed_pt / A3W)
    sy = 1.0 + (2.0 * bleed_pt / A3H)
    s = max(sx, sy)

    # 关键：绕页面中心缩放 => 先把坐标系移到中心，再 scale，再移回去
    cx, cy = A3W / 2.0, A3H / 2.0
    center_scale = (
        Transformation()
        .translate(-cx, -cy)   # 把原点移到页面中心
        .scale(s)              # 围绕中心放大
        .translate(cx, cy)     # 移回
    )
    # 注意：这里不再做 (-bleed, -bleed) 的额外平移，中心缩放已经保证四边等量外溢

    for i in range(num_pages // 2):
        # 基底 A3：先按原尺寸摆好左右两页
        base = PageObject.create_blank_page(width=A3W, height=A3H)

        if i % 2 == 0:
            left_page  = a4_pages[num_pages - 1 - i]
            right_page = a4_pages[i]
        else:
            left_page  = a4_pages[i]
            right_page = a4_pages[num_pages - 1 - i]

        base.merge_transformed_page(left_page,  Transformation().translate(*LEFT_ORIGIN))
        base.merge_transformed_page(right_page, Transformation().translate(*RIGHT_ORIGIN))

        # 真正写入的 A3 页面：绕中心等比放大（对称抵消出血）
        canvas = writer.add_blank_page(width=A3W, height=A3H)
        canvas.merge_transformed_page(base, center_scale)


def parse_args(argv: List[str]):
    """
    参数：
      <input.pdf>（必填）
      [booklet_pages]（可选；4 的倍数）
      [--anti-bleed=0.14]（可选；单位英寸）
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

    # 1) 规范化为 A4（中心裁切/垫白 + 正确处理 mediabox 偏移与 /Rotate）
    normalized_a4_pages: List[PageObject] = [normalize_to_a4(p) for p in reader.pages]

    # 2) 放入扩展器，便于分组补空白
    extender = PdfWriter()
    for p in normalized_a4_pages:
        extender.add_page(p)

    # 3) 计算分组并补足到 4 的倍数（空白 A4）
    groups = compute_groups(total_pages, booklet_pages)
    a4w, a4h = float(PaperSize.A4.width), float(PaperSize.A4.height)

    page_cursor = 0
    for gsize in groups:
        have = len(extender.pages) - page_cursor
        while have < gsize:
            extender.add_blank_page(width=a4w, height=a4h)
            have += 1
        page_cursor += gsize

    # 4) 逐组拼为 A3 横向小册子，并做“放大抵消出血”
    writer = PdfWriter()
    cursor = 0
    for gsize in groups:
        group_slice = [extender.pages[i] for i in range(cursor, cursor + gsize)]
        add_booklet(writer, group_slice, anti_bleed_inch=anti_bleed_inch)
        cursor += gsize

    # 5) 输出
    base, ext = os.path.splitext(filename)
    outname = f"{base}-booklet.pdf"
    with open(outname, "wb") as fp:
        writer.write(fp)
    print(f"输出完成: {outname}")


if __name__ == "__main__":
    main()
