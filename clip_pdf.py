#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
从 PDF 中截取一页的“有内容区域”，直接导出为高 PPI 的 JPEG。

依赖：
    pip install pymupdf
用法示例：
    python pdf_crop_to_jpeg.py input.pdf output.jpg 0 300 5
    # 第 1 页 (索引0)，300dpi，额外留白边 5
"""

import sys
import fitz  # PyMuPDF


def crop_page_to_jpeg(input_pdf, output_jpeg,
                      page_index=0, dpi=300, margin=5):
    """
    将 input_pdf 中的第 page_index 页的内容区域裁切出来，
    并以指定 dpi 渲染为 JPEG，保存到 output_jpeg。

    :param input_pdf: 输入 PDF 路径
    :param output_jpeg: 输出 JPEG 路径
    :param page_index: 页索引（0 开始）
    :param dpi: 输出 JPEG 的分辨率（PPI）
    :param margin: 在内容外额外保留的白边（单位：PDF 坐标，约等于 pt）
    """
    doc = fitz.open(input_pdf)

    if page_index < 0 or page_index >= len(doc):
        raise IndexError(f"页索引超出范围：{page_index}（共 {len(doc)} 页）")

    page = doc[page_index]

    # 获取页面上的文本块（也会包含图片块）
    blocks = page.get_text("blocks")

    if not blocks:
        print("页面未检测到文本块，可能为空页或纯矢量页面，将整页导出为 JPEG。")
        content_rect = page.rect
    else:
        # blocks: (x0, y0, x1, y1, text, block_no, block_type)
        xs0 = [b[0] for b in blocks]
        ys0 = [b[1] for b in blocks]
        xs1 = [b[2] for b in blocks]
        ys1 = [b[3] for b in blocks]

        x0 = min(xs0)
        y0 = min(ys0)
        x1 = max(xs1)
        y1 = max(ys1)

        # 内容外接矩形 + margin
        content_rect = fitz.Rect(
            x0 - margin,
            y0 - margin,
            x1 + margin,
            y1 + margin
        )
        # 防止越界
        content_rect = content_rect & page.rect

    # 计算缩放矩阵：PyMuPDF 默认 72 dpi，dpi/72 即为缩放倍数
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)

    # 渲染为像素图，只裁切内容区域
    pix = page.get_pixmap(matrix=mat, clip=content_rect, alpha=False)

    # 保存为 JPEG
    pix.save(output_jpeg, output="jpeg")
    doc.close()
    print(
        f"已将第 {page_index + 1} 页的内容区域导出为 JPEG：{output_jpeg} (约 {dpi} DPI)"
    )


def main():
    if len(sys.argv) < 3:
        print("用法：python pdf_crop_to_jpeg.py input.pdf output.jpg [page_index] [dpi] [margin]")
        print("  page_index 默认 0（第 1 页）")
        print("  dpi 默认 300")
        print("  margin 默认 5")
        sys.exit(1)

    input_pdf = sys.argv[1]
    output_jpeg = sys.argv[2]
    page_index = int(sys.argv[3]) if len(sys.argv) >= 4 else 0
    dpi = int(sys.argv[4]) if len(sys.argv) >= 5 else 300
    margin = float(sys.argv[5]) if len(sys.argv) >= 6 else 5.0

    crop_page_to_jpeg(input_pdf, output_jpeg, page_index, dpi, margin)


if __name__ == "__main__":
    main()
