#!/bin/bash

gs -o output.pdf -sDEVICE=pdfwrite -c "/setrgbcolor {pop pop pop 0 setgray} bind def" -f $1 
