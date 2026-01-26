import os
import sys
import fitz  # PyMuPDF
from PIL import Image, ImageChops


def get_content_bbox(img):
    """
    获取图像中“非背景”的最小外接矩形 bbox。
    背景色取左上角像素。
    返回 (left, upper, right, lower) 或 None
    """
    bg_color = img.getpixel((0, 0))
    bg = Image.new(img.mode, img.size, bg_color)

    diff = ImageChops.difference(img, bg)
    bbox = diff.getbbox()
    return bbox


def pdf_to_uniform_cropped_images(
    pdf_path,
    output_dir=None,
    dpi=150,
    extra_top_bottom=20  # 上下额外多留的像素
):
    # 如果没指定输出目录，就在 PDF 同目录下建一个同名文件夹
    if output_dir is None:
        base_name = os.path.splitext(os.path.basename(pdf_path))[0]
        output_dir = os.path.join(os.path.dirname(pdf_path), base_name + "_pages")

    os.makedirs(output_dir, exist_ok=True)

    doc = fitz.open(pdf_path)
    page_count = doc.page_count

    # ---------- 第一遍：找到内容区域最大的那一页 ----------
    max_area = 0
    template_bbox = None

    print("第一遍：计算每页内容区域，选择最大的那一页作为裁剪模板...")

    zoom = dpi / 72  # 72 是 PDF 默认分辨率
    mat = fitz.Matrix(zoom, zoom)

    for i in range(page_count):
        page = doc.load_page(i)
        pix = page.get_pixmap(matrix=mat)

        # 转 PIL Image
        mode = "RGBA" if pix.alpha else "RGB"
        img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)

        bbox = get_content_bbox(img)
        if bbox is None:
            # 这一页可能是全空白，跳过
            continue

        left, upper, right, lower = bbox
        w = right - left
        h = lower - upper
        area = w * h

        if area > max_area:
            max_area = area
            template_bbox = bbox

    if template_bbox is None:
        print("未能检测到任何内容区域，可能是空白 PDF？将不进行裁剪，直接导出整页。")
    else:
        print(f"选中的最大内容页 bbox: {template_bbox}, 面积: {max_area}")

    # ---------- 第二遍：按选中的 bbox 统一裁剪并导出 ----------
    print("第二遍：按统一裁剪框导出所有页面图片...")

    for i in range(page_count):
        page = doc.load_page(i)
        pix = page.get_pixmap(matrix=mat)

        mode = "RGBA" if pix.alpha else "RGB"
        img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)

        if template_bbox is not None:
            left, upper, right, lower = template_bbox

            # 上下多留一些
            upper = max(upper - extra_top_bottom, 0)
            lower = min(lower + extra_top_bottom, img.height)

            # 横向简单 clamp 一下，防止越界
            left = max(left, 0)
            right = min(right, img.width)

            crop_box = (left, upper, right, lower)
            img = img.crop(crop_box)

        # 页码从 1 开始命名
        page_num = i + 1
        img_path = os.path.join(output_dir, f"{page_num}.png")
        img.save(img_path)
        print(f"已保存: {img_path}")

    doc.close()
    print(f"完成！共导出 {page_count} 页到文件夹：{output_dir}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python pdf2img_uniform_crop.py your.pdf [输出文件夹] [dpi] [extra_top_bottom]")
        print("示例: python pdf2img_uniform_crop.py test.pdf out_pages 200 40")
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) >= 3 else None
    dpi = int(sys.argv[3]) if len(sys.argv) >= 4 else 150
    extra_top_bottom = int(sys.argv[4]) if len(sys.argv) >= 5 else 20

    pdf_to_uniform_cropped_images(pdf_path, output_dir, dpi, extra_top_bottom)

