#!/usr/bin/env bash
# -----------------------------------------------
# 背景视频优化脚本 optimize_video.sh
# 支持：
#   - 等比缩放到不超过 MAX_HEIGHT (默认 1080)
#   - H.264 编码 (libx264) + CRF 自适应码率
#   - 去音轨 (-an) 降低体积（你首页视频是 muted）
#   - faststart 移动 moov 到文件头，提升首帧播放速度
#   - 控制输出帧率 (FPS) 降低解码压力
#   - 原/新大小与压缩百分比报告
# 环境变量可覆盖：CRF PRESET FPS MAX_HEIGHT KEEP_AUDIO(=1 保留音轨) THREADS
# 用法：
#   bash scripts/optimize_video.sh 输入文件 [输出文件]
# 例：
#   bash scripts/optimize_video.sh static/video/bg_source.mp4 static/video/bg.mp4
# 若省略输出文件 → 默认 static/video/bg.mp4
# -----------------------------------------------
set -euo pipefail

command -v ffmpeg >/dev/null 2>&1 || { echo "[错误] 未找到 ffmpeg，请先安装" >&2; exit 2; }
command -v ffprobe >/dev/null 2>&1 || { echo "[错误] 未找到 ffprobe，请先安装" >&2; exit 2; }

INFILE="${1:-}"
OUTFILE="${2:-static/video/bg.mp4}"
CRF="${CRF:-23}"
PRESET="${PRESET:-slow}"
FPS="${FPS:-30}"
MAX_HEIGHT="${MAX_HEIGHT:-1080}"
KEEP_AUDIO="${KEEP_AUDIO:-0}"
THREADS="${THREADS:-0}"  # 0 = ffmpeg 自动

if [[ -z "$INFILE" || ! -f "$INFILE" ]]; then
  echo "[错误] 输入文件不存在: $INFILE" >&2; exit 1; fi

mkdir -p "$(dirname "$OUTFILE")"

read -r ORIG_W ORIG_H < <(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of default=noprint_wrappers=1:nokey=1 "$INFILE" | tr '\n' ' ')

if [[ -z "${ORIG_W}" || -z "${ORIG_H}" ]]; then
  echo "[警告] ffprobe 无法解析分辨率，使用自适应缩放过滤器（仅在高度>MAX_HEIGHT时降采样）。";
  # 自适应：若 ih>MAX_HEIGHT 则限制高度为 MAX_HEIGHT，宽度按 -2 保持偶数等比；否则保持原始分辨率（不放大）
  SCALE_FILTER="scale='if(gt(ih,${MAX_HEIGHT}),-2,iw)':'if(gt(ih,${MAX_HEIGHT}),${MAX_HEIGHT},ih)'"
else
  if (( ORIG_H > MAX_HEIGHT )); then
    SCALE_FILTER="scale=-2:${MAX_HEIGHT}"
    echo "[信息] 缩放: ${ORIG_W}x${ORIG_H} → 高度限制 ${MAX_HEIGHT}";
  else
    SCALE_FILTER="scale=${ORIG_W}:${ORIG_H}";
    echo "[信息] 保持原始分辨率: ${ORIG_W}x${ORIG_H}";
  fi
fi

if (( KEEP_AUDIO == 1 )); then
  AUDIO_OPTS="-c:a aac -b:a 128k"
  echo "[信息] 保留音轨 (AAC 128k)";
else
  AUDIO_OPTS="-an"
  echo "[信息] 去除音轨";
fi

TMPFILE="$(dirname "$OUTFILE")/.tmp.$(basename "$OUTFILE")"
cleanup() { rm -f "$TMPFILE" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "[执行] ffmpeg 编码 (CRF=$CRF PRESET=$PRESET FPS=$FPS MAX_HEIGHT=$MAX_HEIGHT)";
ffmpeg -y -i "$INFILE" -c:v libx264 -preset "$PRESET" -crf "$CRF" -r "$FPS" -vf "$SCALE_FILTER" -movflags +faststart $AUDIO_OPTS -threads "$THREADS" -f mp4 "$TMPFILE"

ORIG_SIZE=$(stat -c %s "$INFILE")
NEW_SIZE=$(stat -c %s "$TMPFILE")
PCT=$(awk -v o=$ORIG_SIZE -v n=$NEW_SIZE 'BEGIN{printf "%.1f", (1-n/o)*100}')
mv "$TMPFILE" "$OUTFILE"
trap - EXIT INT TERM
echo "[完成] 输出: $OUTFILE"
echo "         原大小: $ORIG_SIZE bytes"
echo "         新大小: $NEW_SIZE bytes (减少: $PCT%)"
echo "[提示] 后续执行: python manage.py collectstatic --noinput 刷新静态 manifest"