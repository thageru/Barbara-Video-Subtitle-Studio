# 一键启动交付说明

## 用户入口

macOS 用户双击项目根目录的 `Barbara-Video-Subtitle-Studio.command` 即可启动。脚本会：

1. 定位项目目录，不依赖当前终端所在路径。
2. 优先使用 `.venv/bin/python`，没有时回退到系统 `python3`。
3. 检查 `ffmpeg` 与 `whisperkit-cli`，用普通语言提示缺少的运行工具。
4. 确认已随发布包提供的 `video_tool/static/index.html` 存在。
5. 启动本地服务并自动打开浏览器。
6. 跟踪打开的工作台页面；关闭最后一个页面后，在没有运行中任务时自动结束本地监听服务。

前端构建产物被纳入 Git，因此最终用户不需要 Node.js/npm。只有修改 `frontend/` 源码时，开发者才需要运行 `npm install` 和 `npm run build`。

## 运行依赖

- Python 3
- `ffmpeg`（预览、硬字幕和视频输出）
- `whisperkit-cli`（生成英文字幕）

翻译页不需要 API 配置。页面会生成“翻译模板 + 完整英文 SRT”，用户把它复制到任意 AI，随后将返回的完整目标语言 SRT 粘贴回来即可。

页面右上角的关闭按钮用于立即停服。普通刷新、主页与字幕编辑页之间的跳转、以及关闭多个标签页中的一个，都不会误关仍在使用的服务。
