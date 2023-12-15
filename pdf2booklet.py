#!python3
from pypdf import PdfWriter, PdfReader, PaperSize, Transformation
import sys

# sourcepage = reader.pages[0]

# print(sourcepage.cropbox.lower_left)
# print(sourcepage.cropbox.lower_right)
# print(sourcepage.cropbox.upper_left)
# print(sourcepage.cropbox.upper_right)

# destpage = writer.add_blank_page(width=PaperSize.A3.height, height=PaperSize.A3.width)

# print(destpage.cropbox.lower_left)
# print(destpage.cropbox.lower_right)
# print(destpage.cropbox.upper_left)
# print(destpage.cropbox.upper_right)

# sourcepage.cropbox = destpage.cropbox
# sourcepage.mediabox = destpage.mediabox
# destpage.merge_page(sourcepage)
# sourcepage.add_transformation(
#     Transformation().translate(
#         PaperSize.A4.width,
#         0,
#     )
# )
# destpage.merge_page(sourcepage)

# with open("output.pdf", "wb") as fp:
#     writer.write(fp)
def add_booklet(writer, pages):
    num_pages = len(pages)

    if pages[0].mediabox.width > PaperSize.A4.width:
        left_x_offset = (PaperSize.A4.width - pages[0].mediabox.width) / 2
        right_x_offset = (PaperSize.A4.width - pages[0].mediabox.width) / 2 + PaperSize.A4.width
    else:
        left_x_offset = (PaperSize.A4.width - pages[0].mediabox.width)
        right_x_offset = PaperSize.A4.width

    y_offset = (PaperSize.A4.height - pages[0].mediabox.height) / 2

    for i in range(num_pages // 2):
        new_page = writer.add_blank_page(width=PaperSize.A3.height, height=PaperSize.A3.width)
        if (i % 2 == 0):
            left_page = pages[num_pages - i - 1]
            right_page = pages[i]
        else:
            left_page = pages[i]
            right_page = pages[num_pages - i - 1]

        left_page.cropbox = new_page.cropbox
        left_page.mediabox = new_page.mediabox
        right_page.cropbox = new_page.cropbox
        right_page.mediabox = new_page.mediabox
        
        left_page.add_transformation(
            Transformation().translate(
                left_x_offset,
                y_offset,
            )
        )

        right_page.add_transformation(
            Transformation().translate(
                right_x_offset,
                y_offset,
            )
        )
        
        new_page.merge_page(left_page)
        new_page.merge_page(right_page)
        
    
def main():
    # preproccessing the input, make it align to the booklet pages
    args = sys.argv
    filename = args[1]
    reader = PdfReader(filename)
    extender = PdfWriter()
    writer = PdfWriter()

    if (len(args) > 2):
        booklet_pages = int(args[2])
        if (booklet_pages % 4 != 0):
            print("Number of booklet pages must be a multiple of 4")
            return
    else:
        print("No specified number of booklet pages")
        booklet_pages = 20
    
    extender.append(reader)

    while (len(extender.pages) % booklet_pages != 0):
        extender.add_blank_page(width=reader.pages[0].mediabox.width, height=reader.pages[0].mediabox.height)

    with open("inter.pdf", "wb") as fp:
        extender.write(fp)

    reader = PdfReader("inter.pdf")
    # sort the pages
    for i in range(len(reader.pages) // booklet_pages):
        add_booklet(writer, reader.pages[i * booklet_pages : (i + 1) * booklet_pages])

    with open("output.pdf", "wb") as fp:
        writer.write(fp)

if __name__ == "__main__":
    main()
