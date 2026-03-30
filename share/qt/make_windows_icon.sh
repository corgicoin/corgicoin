#!/bin/bash
# create multiresolution windows icon
ICON_SRC=../../src/qt/res/icons/corgicoin.png
ICON_DST=../../src/qt/res/icons/corgicoin.ico
convert ${ICON_SRC} -resize 16x16 corgicoin-16.png
convert ${ICON_SRC} -resize 32x32 corgicoin-32.png
convert ${ICON_SRC} -resize 48x48 corgicoin-48.png
convert corgicoin-16.png corgicoin-32.png corgicoin-48.png ${ICON_DST}
