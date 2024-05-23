import cv2
import sys

args = sys.argv
input_picture_name = args[1]
image = cv2.imread(input_picture_name)

# split the image into two parts
height, width = image.shape[:2]
half_width = width // 2
left_image = image[:, :half_width]
right_image = image[:, half_width:]

# save the two parts
output_picture_name = input_picture_name.split(".")[0]
cv2.imwrite(output_picture_name + "_left.jpg", left_image)
cv2.imwrite(output_picture_name + "_right.jpg", right_image)
