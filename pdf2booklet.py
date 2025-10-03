#!/usr/bin/env python3

import sys
import os
from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import RectangleObject
from pypdf import PageObject

class PaperSize:
    A4 = RectangleObject([0, 0, 595.276, 841.890])   # 72 dpi points
    A3 = RectangleObject([0, 0, 841.890, 1190.551])  # 72 dpi points

def add_booklet(writer, pages):
    num_pages = len(pages)

    # 确保页面不大于 A4，超过就裁剪
    fixed_pages = []
    for p in pages:
        if p.mediabox.width > PaperSize.A4.width or p.mediabox.height > PaperSize.A4.height:
            newp = PageObject.create_blank_page(width=PaperSize.A4.width, height=PaperSize.A4.height)
            tmp = p
            tmp.add_transformation(
                Transformation().translate(
                    (PaperSize.A4.width - p.mediabox.width) / 2,
                    (PaperSize.A4.height - p.mediabox.height) / 2
                )
            )
            newp.merge_page(tmp)
            fixed_pages.append(newp)
        else:
            fixed_pages.append(p)

    # 偏移量
    left_x_offset = (PaperSize.A4.width - fixed_pages[0].mediabox.width)
    right_x_offset = PaperSize.A4.width
    y_offset = (PaperSize.A4.height - fixed_pages[0].mediabox.height) / 2

    for i in range(num_pages // 2):
        new_page = writer.add_blank_page(width=PaperSize.A3.height, height=PaperSize.A3.width)
        if (i % 2 == 0):
            left_page = fixed_pages[num_pages - i - 1]
            right_page = fixed_pages[i]
        else:
            left_page = fixed_pages[i]
            right_page = fixed_pages[num_pages - i - 1]

        lp = PageObject.create_blank_page(width=PaperSize.A3.height, height=PaperSize.A3.width)
        lp.merge_page(left_page)
        lp.add_transformation(Transformation().translate(left_x_offset, y_offset))

        rp = PageObject.create_blank_page(width=PaperSize.A3.height, height=PaperSize.A3.width)
        rp.merge_page(right_page)
        rp.add_transformation(Transformation().translate(right_x_offset, y_offset))

        new_page.merge_page(lp)
        new_page.merge_page(rp)

def main():
    args = sys.argv
    filename = args[1]
    reader = PdfReader(filename)
    extender = PdfWriter()
    writer = PdfWriter()

    total_pages = len(reader.pages)

    if (len(args) > 2):
        # 用户指定了页数
        booklet_pages = int(args[2])
        if (booklet_pages % 4 != 0):
            print("Number of booklet pages must be a multiple of 4")
            return
        group_sizes = [booklet_pages] * ((total_pages + booklet_pages - 1) // booklet_pages)
    else:
        # 自动分组逻辑
        if total_pages <= 20:
            # 一次性做完，补齐到4的倍数
            group_size = ((total_pages + 3) // 4) * 4
            group_sizes = [group_size]
        else:
            # 前面的都是20页一组
            num_full_groups = total_pages // 20
            remainder = total_pages % 20

            group_sizes = [20] * num_full_groups
            if remainder > 0:
                last_group_size = ((remainder + 3) // 4) * 4
                group_sizes.append(last_group_size)

    # 把原始页拷贝进来
    extender.append(reader)

    # 按照 group_sizes 补齐每组空白页
    page_cursor = 0
    for gsize in group_sizes:
        while (len(extender.pages) - page_cursor) < gsize:
            extender.add_blank_page(width=PaperSize.A4.width, height=PaperSize.A4.height)
        page_cursor += gsize

    # 再次生成小册子
    cursor = 0
    for gsize in group_sizes:
        add_booklet(writer, extender.pages[cursor:cursor+gsize])
        cursor += gsize

    # 输出文件名
    base, ext = os.path.splitext(filename)
    outname = f"{base}-booklet.pdf"
    with open(outname, "wb") as fp:
        writer.write(fp)
    print(f"输出完成: {outname}")

if __name__ == "__main__":
    main()
