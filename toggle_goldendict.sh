#!/usr/bin/env bash
set -euo pipefail

# ====== 可配置项 ======
# 优先匹配的窗口标题前缀 / 类名片段（大小写不敏感）
WIN_TITLE_PREFIX="${WIN_TITLE_PREFIX:-GoldenDict}"
WIN_CLASS_HINT="${WIN_CLASS_HINT:-goldendict}"

# 候选启动命令（按顺序尝试；找到第一个就用它）
CANDIDATES=(
  "goldendict"                               # 传统包
  "goldendict-ng"                            # NG
  "flatpak run org.goldendict.GoldenDict"    # 常见 Flathub ID
  "flatpak run io.github.xiaoyifang.goldendict-qt5"  # 另一常见 Flathub ID
)
# 启动后等待应用建窗的时间（秒）
SPAWN_WAIT="${SPAWN_WAIT:-0.8}"

# ====== 辅助函数 ======
log(){ printf '[toggle-gd] %s\n' "$*" >&2; }

pick_launch_cmd() {
  for c in "${CANDIDATES[@]}"; do
    if [[ "$c" == flatpak* ]]; then
      # flatpak 情况：有 flatpak 且该 ID 存在才算有效
      command -v flatpak >/dev/null 2>&1 || continue
      local app_id; app_id=$(awk '{print $3}' <<<"$c")
      flatpak info "$app_id" >/dev/null 2>&1 && { echo "$c"; return 0; }
    else
      command -v "${c%% *}" >/dev/null 2>&1 && { echo "$c"; return 0; }
    fi
  done
  return 1
}

have_qdbus() {
  command -v qdbus >/dev/null 2>&1 && { echo qdbus; return; }
  command -v qdbus6 >/dev/null 2>&1 && { echo qdbus6; return; }
  command -v qdbus-qt5 >/dev/null 2>&1 && { echo qdbus-qt5; return; }
  return 1
}

# ====== 确认 KWin D-Bus 可达 ======
QDBUS_BIN="$(have_qdbus || true)"
if [[ -z "${QDBUS_BIN:-}" ]]; then
  log "❌ 找不到 qdbus（qt6-tools 或 qt5-tools 未安装？）"
  exit 1
fi
if ! "$QDBUS_BIN" org.kde.KWin /KWin org.kde.KWin.supportInformation >/dev/null 2>&1; then
  log "❌ org.kde.KWin D-Bus 不可达（会话总线或 KWin 异常）"
  exit 2
fi

# ====== 先跑一次 KWin 切换（如果已开就直接切换） ======
run_kwin_toggle() {
  local js
  js=$(mktemp /tmp/toggle_gd_kwin.XXXXXX.js)
  cat >"$js"<<'KWINJS'
function L(){ print("[KWIN][toggle-gd]", Array.prototype.join.call(arguments," ")); }
function toggle(){
  var titlePrefix="%TITLE_PREFIX%";
  var classHint="%CLASS_HINT%".toLowerCase();

  L("start titlePrefix=",titlePrefix," classHint=",classHint);

  var wins = (workspace.stackingOrder || []);
  L("windows(stackingOrder) count=", wins.length);

  var target=null;
  for (var i=0;i<wins.length;i++){
    var w=wins[i];
    var cap=(w.caption||"");
    var cls=((w.resourceName||"")+" "+(w.windowClass||"")).toLowerCase();
    L("WIN#",i,"cap=",cap," resourceName=",w.resourceName," windowClass=",w.windowClass," minimized=",w.minimized," managed=",w.managed);
    var hit=false;
    if (titlePrefix && cap.indexOf(titlePrefix)===0) hit=true;
    if (!hit && classHint && cls.indexOf(classHint)!==-1) hit=true;
    if (hit){ target=w; L("HIT#",i); break; }
  }

  if (target){
    if (target.minimized){ L("action: unminimize+activate"); target.minimized=false; workspace.activeWindow=target; }
    else if (workspace.activeWindow===target){ L("action: minimize (hide)"); target.minimized=true; }
    else { L("action: activate"); workspace.activeWindow=target; }
    L("done"); return true;
  }
  L("no matching window");
  return false;
}
toggle();
KWINJS

  sed -i "s|%TITLE_PREFIX%|${WIN_TITLE_PREFIX//|/\\|}|" "$js"
  sed -i "s|%CLASS_HINT%|${WIN_CLASS_HINT//|/\\|}|" "$js"

  local id rc=0
  id=$("$QDBUS_BIN" org.kde.KWin /Scripting org.kde.kwin.Scripting.loadScript "$js")
  "$QDBUS_BIN" org.kde.KWin "/Scripting/Script${id}" org.kde.kwin.Script.run || rc=$?
  # 不立刻 stop，避免日志被截断；但为了清理，轻微延时后再停
  sleep 0.2
  "$QDBUS_BIN" org.kde.KWin "/Scripting/Script${id}" org.kde.kwin.Script.stop >/dev/null 2>&1 || true
  return $rc
}

# 先尝试直接切换（如果窗口已存在）
log "尝试直接切换（若已在运行会立即响应）……"
if run_kwin_toggle; then
  log "✅ 已完成切换/最小化/还原"
  exit 0
fi

# 没有窗口 → 启动进程（用我们自己挑的命令）
LAUNCH_CMD="$(pick_launch_cmd || true)"
if [[ -z "${LAUNCH_CMD:-}" ]]; then
  log "❌ 找不到可用的 Goldendict 启动方式（既无 goldendict/goldendict-ng，也无对应 flatpak）"
  exit 3
fi
log "未发现窗口，准备启动：$LAUNCH_CMD"
# 注意：不走 klauncher，直接从 shell 拉起，规避 desktop-id/环境差异
( nohup bash -lc "$LAUNCH_CMD >/dev/null 2>&1 &" ) >/dev/null 2>&1 || true

# 等待进程建窗
sleep "$SPAWN_WAIT"

# 再次切换（此时应能命中并激活）
log "再次尝试切换……"
run_kwin_toggle || true
