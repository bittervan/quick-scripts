#!/usr/bin/env bash

SRC_DIR="$1"
DST_DIR="$2"

if [ -z "$SRC_DIR" ] || [ -z "$DST_DIR" ]; then
  echo "用法: $0 <dsf目录> <输出flac目录>"
  exit 1
fi

find "$SRC_DIR" -type f -iname "*.dsf" | while read -r f; do
  rel="${f#$SRC_DIR/}"
  out="$DST_DIR/${rel%.dsf}.flac"

  mkdir -p "$(dirname "$out")"

  echo "转换: $f -> $out"

  ffmpeg -y \
    -i "$f" \
    -map_metadata 0 \
    -c:a flac \
    -compression_level 8 \
    "$out"
done

