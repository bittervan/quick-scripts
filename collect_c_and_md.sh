#!/usr/bin/env bash
# 用法：./collect.sh /path/to/src /path/to/out_dir
set -euo pipefail
src="${1:-.}"
dst="${2:-./rag_src}"
mkdir -p "$dst"
manifest="$dst/_manifest.tsv"
: > "$manifest"

find "$src" \
  -type d \( -name .git -o -name build -o -name out -o -name node_modules \) -prune -o \
  -type f \( -iname '*.c' -o -iname '*.cpp' -o -iname '*.h' -o -iname '*.hpp' -o -iname '*.md' \) -print0 |
while IFS= read -r -d '' f; do
  base=$(basename "$f")
  out="$dst/$base"
  if [[ -e "$out" ]]; then
    # 同名文件：在文件名后追加路径哈希避免覆盖
    hash=$(printf '%s' "$f" | sha1sum | cut -c1-8)
    ext="${base##*.}"; name="${base%.*}"
    out="$dst/${name}__${hash}.${ext}"
  fi
  cp -p -- "$f" "$out"
  printf "%s\t%s\n" "$out" "$f" >> "$manifest"
done

echo "OK → 文件在：$dst"
echo "映射清单：$manifest（新文件名\t原始完整路径）"

