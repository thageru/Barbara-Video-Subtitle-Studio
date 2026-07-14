# Barbara-Video-Subtitle-Studio

本项目是一个本地视频字幕处理工具，提供两个入口：

- Web UI：适合选择本地视频、生成英文字幕、翻译/手动编辑字幕、预览并输出外挂或硬字幕视频。
- CLI：适合批处理、脚本化和更清晰的错误输出。

## 推荐工作流

不要让 WhisperKit 直接生成中文字幕。当前推荐流程是：

1. 从视频生成英文 `.en.srt`。
2. 在翻译页生成“翻译模板 + 完整英文 SRT”提示词，复制到任意 AI 或交给人工翻译。
3. 将返回的完整目标语言 SRT 原样粘贴回页面。系统校验条目、序号和时间码后生成 `zh-Hans` SRT。
4. 在本地播放器实时检查字幕时间轴和位置，并可生成与最终烧录完全一致的 ffmpeg 预览帧。
5. 选择外挂字幕、硬烧录，或移除原视频中的内嵌软字幕。

这个流程把“语音识别”和“翻译质量控制”拆开，避免 Whisper 中文直出导致繁体字和机翻质量问题。

## 架构

- `video_tool/transcriber.py`：调用 WhisperKit 生成 SRT。英文字幕使用 `transcribe --language en`。
- `video_tool/translator.py`：生成带完整英文 SRT 的翻译模板，校验并导入其他 AI 或人工返回的目标语言 SRT。
- `video_tool/srt.py`：解析、写入、手动翻译和双语 SRT 导出。
- `video_tool/processor.py`：ffmpeg 预览、外挂字幕复制、硬字幕烧录和内嵌软字幕移除；预览和硬烧录共用同一套字幕样式。
- `video_tool/web.py`：本地 Web UI、任务队列、本地视频流式预览、文件选择和关闭服务。
- `video_tool/cli.py`：命令行入口。
- `docs/design-system.md`：Web 工作台的颜色、间距、交互和响应式设计约束。

## 离线运行前提

字幕生成依赖本机 `whisperkit-cli`。硬字幕预览/烧录依赖支持 `subtitles`/`libass` 的 `ffmpeg`。

请确保 `ffmpeg` 可从 `PATH` 使用。如果安装在其他位置，运行前设置：

```bash
export FFMPEG_BIN=/path/to/ffmpeg
```

项目不保存任何翻译 API 地址或密钥。翻译提示词由页面生成，用户可以复制到任意 AI，也可以直接人工编辑；导入、校验、预览和输出全部在本机完成。

## Web UI（一键启动）

### 普通用户：双击启动

在 macOS Finder 中双击项目根目录里的 `Barbara-Video-Subtitle-Studio.command`。启动器会自动选择项目自带的 Python 虚拟环境（如果存在），否则使用系统 Python，并打开本地工作台。

本分支已经附带编译好的 React 前端，因此普通用户不需要安装 Node.js 或 npm。启动器会在缺少 `ffmpeg` 或 `whisperkit-cli` 时给出清晰提示；字幕生成、预览和视频导出分别需要这些工具。

如果 macOS 第一次阻止打开，请右键该文件并选择“打开”。终端窗口请保持打开；点击页面右上角的 `Close Service` 会立即停止服务，关闭最后一个工作台页面也会自动停止服务。

### 开发者：重新构建前端

只有需要修改 React 界面时才需要 Node.js：

```bash
cd frontend
npm install
npm run build
```

构建结果会写入 `video_tool/static/`，Python 服务会自动托管该目录。

启动：

```bash
cd Barbara-Video-Subtitle-Studio
python3 run_web.py --port 8876 --open
```

默认地址是 `http://127.0.0.1:8876/`。应用完全在本机运行；背景视频是远程视觉资源，网络不可用时会自动降级为静态深色背景。

页面右上角提供中英文切换按钮，选择会保存在浏览器本地，下次打开继续使用上次语言。

页面主要工作区：

1. `Generate English SRT`：选择视频后创建同名文件夹，输出 `视频名/视频名.en.srt`。
2. `Translate English SRT`：选择 `.en.srt`，生成并复制带完整字幕内容的翻译提示词；将其他 AI 返回的完整 SRT 粘贴回来后生成 `视频名.zh-Hans.srt`。
3. `Preview and Finalize`：流式播放本地视频并实时叠加 SRT，调整字体和位置；确认后选择硬烧录、外挂字幕或移除内嵌软字幕。
4. `在线编辑已有字幕`：选择任意 `.srt`，在线修改文本并保留原序号和时间轴，可覆盖保存或另存。

所有生成文件统一存入以初始视频名称命名的文件夹。例如选择 `/Videos/demo.mp4` 后，英文字幕、翻译字幕和输出视频都会写入 `/Videos/demo/`。任务完成或失败后，页面顶部会实时更新提示。

字幕位置参数是“距离底部的百分比”。例如 720p 视频里 `10%` 会换算成 `MarginV=72`。预览帧和硬烧录使用同一套 ffmpeg filter，因此页面看到的字幕位置和最终视频一致。

停止服务：页面右上角点击 `Close Service` 会立即停止本地 Python 监听服务，并把页面切换为明确的“服务已停止”状态。关闭最后一个工作台标签页后，服务也会在短暂宽限期后自动退出；刷新页面、站内跳转或仍有其他工作台标签页时不会误停。如果后台任务尚未完成，自动退出会等待任务结束。也可以在终端按 `Ctrl+C`。

## CLI

检查环境：

```bash
cd Barbara-Video-Subtitle-Studio
python3 videoctl.py doctor
```

生成英文字幕：

```bash
python3 videoctl.py subtitles \
  --video /path/to/video.mp4 \
  --languages en
```

外挂字幕：

```bash
python3 videoctl.py process \
  --video /path/to/video.mp4 \
  --subtitle /path/to/video.zh-Hans.srt \
  --mode external \
  --language zh-Hans
```

硬烧录并设置样式：

```bash
python3 videoctl.py process \
  --video /path/to/video.mp4 \
  --subtitle /path/to/video.zh-Hans.srt \
  --mode burn \
  --language zh-Hans \
  --font-size 22 \
  --subtitle-y 2
```

移除视频中的内嵌软字幕轨道（视频和音频不重新编码）：

```bash
python3 videoctl.py process \
  --video /path/to/video-with-soft-subs.mp4 \
  --mode strip-soft
```

## 当前边界

- 内嵌软字幕可以无损移除；硬字幕已经是画面像素，不能无损剥离。
- Web UI 的任务状态保存在内存里，重启服务后会清空。
- `burn` 模式会重新编码视频；`external` 模式只复制字幕文件；`strip-soft` 只重新封装并移除字幕流。
- `zh-Hans` 会强制规范化为简体中文，避免翻译或识别结果混入繁体字。
