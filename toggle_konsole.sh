#!/usr/bin/env bash
# Toggle Konsole on KDE/Wayland via qdbus (QWidget props + visibility), with state fallback.
# Usage: ./toggle_konsole.sh [-v]
set -euo pipefail
VERBOSE=0
[[ "${1:-}" == "-v" ]] && VERBOSE=1
log()  { printf '[konsole-toggle] %s\n' "$*"; }
vlog() { [[ "$VERBOSE" -eq 1 ]] && log "$*" || true; }

QDBUS="${QDBUS_BIN:-$(command -v qdbus6 || command -v qdbus-qt5 || command -v qdbus || true)}"
[[ -z "${QDBUS}" ]] && { log "ERROR: qdbus not found"; exit 1; }

# 1) 列出 Konsole 服务（用标准 DBus API）
mapfile -t SERVICES < <(
  "$QDBUS" org.freedesktop.DBus / org.freedesktop.DBus.ListNames \
    | tr ' ' '\n' | grep -E '^org\.kde\.konsole($|-)'
)
[[ ${#SERVICES[@]} -eq 0 ]] && { log "ERROR: no org.kde.konsole service"; exit 2; }

# 2) 在每个服务里找主窗口对象
find_obj() {
  local svc="$1" obj
  obj="$("$QDBUS" "$svc" 2>/dev/null | grep -E '^/konsole/MainWindow_[0-9]+' | head -n1 || true)"
  [[ -z "$obj" ]] && obj="$("$QDBUS" "$svc" 2>/dev/null | grep -E '^/Windows/[0-9]+' | head -n1 || true)"
  [[ -n "$obj" ]] && echo "$obj"
}
IFACE="org.qtproject.Qt.QWidget"
PIFACE="org.freedesktop.DBus.Properties"
has_qwidget() { "$QDBUS" "$1" "$2" "$IFACE.showNormal" >/dev/null 2>&1; }
get_prop() { "$QDBUS" "$1" "$2" "$PIFACE.Get" "$IFACE" "$3" 2>/dev/null || echo ""; }

CAND=()
for svc in "${SERVICES[@]}"; do
  obj="$(find_obj "$svc" || true)"
  [[ -z "$obj" ]] && continue
  has_qwidget "$svc" "$obj" || { vlog "skip $svc $obj (no QWidget)"; continue; }
  minimized="$(get_prop "$svc" "$obj" minimized)"
  visible="$(get_prop "$svc" "$obj" visible)"
  active="$(get_prop "$svc" "$obj" isActiveWindow)"
  CAND+=("${svc}|${obj}|${minimized}|${visible}|${active}")
done
[[ ${#CAND[@]} -eq 0 ]] && { log "ERROR: no Konsole window with QWidget iface"; exit 3; }

# 3) 选择目标窗口（活动优先→可见未最小化→首个）
pick=-1
for i in "${!CAND[@]}"; do IFS='|' read -r s o m v a <<<"${CAND[$i]}"; [[ "$a" == "true" ]] && { pick=$i; break; }; done
if [[ $pick -lt 0 ]]; then
  for i in "${!CAND[@]}"; do IFS='|' read -r s o m v a <<<"${CAND[$i]}"; [[ "$v" == "true" && "$m" == "false" ]] && { pick=$i; break; }; done
fi
[[ $pick -lt 0 ]] && pick=0
IFS='|' read -r SVC OBJ MIN VIS ACT <<<"${CAND[$pick]}"
log "target: svc=$SVC obj=$OBJ minimized=$MIN visible=$VIS active=$ACT"

STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/konsole-toggle"
STATE_FILE="${STATE_DIR}/$(echo -n "${SVC}${OBJ}" | sha256sum | cut -d' ' -f1).state"
mkdir -p "$STATE_DIR"
prev="$(cat "$STATE_FILE" 2>/dev/null || echo "")"
vlog "prev-state(${STATE_FILE}): ${prev:-<none>}"

# 4) 动作
do_show() {
  "$QDBUS" "$SVC" "$OBJ" "$IFACE.setVisible" true  >/dev/null 2>&1 || true
  "$QDBUS" "$SVC" "$OBJ" "$IFACE.showNormal"       >/dev/null 2>&1 || true
  "$QDBUS" "$SVC" "$OBJ" "$IFACE.raise"            >/dev/null 2>&1 || true
  "$QDBUS" "$SVC" "$OBJ" "$IFACE.setFocus"         >/dev/null 2>&1 || true
  echo "shown" > "$STATE_FILE"
  log "action: SHOW"
}
do_hide() {
  # 先显式隐藏，再最小化（两手准备，适配属性不更新的情况）
  "$QDBUS" "$SVC" "$OBJ" "$IFACE.setVisible" false >/dev/null 2>&1 || true
  "$QDBUS" "$SVC" "$OBJ" "$IFACE.showMinimized"    >/dev/null 2>&1 || true
  echo "hidden" > "$STATE_FILE"
  log "action: HIDE"
}

# 5) 判定：属性优先，必要时用状态兜底
# 属性判定：若最小化(min==true) 或 不可见(visible==false) → SHOW；否则 → HIDE
if [[ "$MIN" == "true" || "$VIS" == "false" ]]; then
  do_show
else
  # 属性看起来“可见未最小化”，但如果上次我们刚刚 HIDE 过，则强制 SHOW（修复属性滞后）
  if [[ "$prev" == "hidden" ]]; then
    vlog "property says visible, but last was hidden → force SHOW"
    do_show
  else
    do_hide
    # 小延迟让属性有时间刷新，避免连续触发时误判
    sleep 0.1
  fi
fi

