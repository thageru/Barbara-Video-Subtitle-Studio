# 一键启动交付说明

## 用户入口

macOS 用户双击项目根目录的 `Barbara-Video-Subtitle-Studio.command` 即可启动。脚本会：

1. 定位项目目录，不依赖当前终端所在路径。
2. 优先使用 `.venv/bin/python`，没有时回退到系统 `python3`。
3. 检查 `ffmpeg` 与 `whisperkit-cli`，用普通语言提示缺少的运行工具。
4. 确认已随发布包提供的 `video_tool/static/index.html` 存在。
5. 启动本地服务并自动打开浏览器。

前端构建产物被纳入 Git，因此最终用户不需要 Node.js/npm。只有修改 `frontend/` 源码时，开发者才需要运行 `npm install` 和 `npm run build`。

## 运行依赖

- Python 3
- `ffmpeg`（预览、硬字幕和视频输出）
- `whisperkit-cli`（生成英文字幕）

翻译 API 仍由用户在页面中配置；也可以使用在线编辑器完成手动翻译，不需要 API。
