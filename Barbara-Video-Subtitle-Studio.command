#!/bin/zsh

# Double-click launcher for Barbara-Video-Subtitle-Studio on macOS.
# Keep this terminal window open so errors remain visible to non-technical users.

set -u

APP_DIR="${0:A:h}"
cd "$APP_DIR" || {
  echo "无法进入应用目录：$APP_DIR"
  read -r "?按回车键退出..."
  exit 1
}

if [[ -x "$APP_DIR/.venv/bin/python" ]]; then
  PYTHON="$APP_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
else
  echo "未找到 Python 3。请先从 https://www.python.org/downloads/macos/ 安装 Python 3。"
  read -r "?安装后按回车键退出..."
  exit 1
fi

echo "Barbara-Video-Subtitle-Studio"
echo "正在启动本地字幕工作台……"
echo ""

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "提示：未找到 ffmpeg。预览、硬字幕和视频导出需要 ffmpeg。"
  echo "可使用 Homebrew 安装：brew install ffmpeg"
  echo ""
fi

if ! command -v whisperkit-cli >/dev/null 2>&1; then
  echo "提示：未找到 whisperkit-cli。生成英文字幕前需要安装 WhisperKit CLI。"
  echo ""
fi

if [[ ! -f "$APP_DIR/video_tool/static/index.html" ]]; then
  echo "前端构建产物缺失：video_tool/static/index.html"
  echo "请从完整发布包启动，或在源码目录执行："
  echo "  cd frontend && npm install && npm run build"
  echo ""
  read -r "?按回车键退出..."
  exit 1
fi

echo "浏览器将打开 http://127.0.0.1:8876/"
echo "关闭页面右上角的 Close Service，或回到此窗口按 Ctrl+C 即可停止。"
echo ""

exec "$PYTHON" "$APP_DIR/run_web.py" --host 127.0.0.1 --port 8876 --open
