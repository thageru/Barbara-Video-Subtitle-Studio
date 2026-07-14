# Barbara-Video-Subtitle-Studio

本项目是一个本地视频字幕处理工具，提供两个入口：

- Web UI：适合选择本地视频、生成英文字幕、翻译/手动编辑字幕、预览并输出外挂或硬字幕视频。
- CLI：适合批处理、脚本化和更清晰的错误输出。

## 推荐工作流

不要让 WhisperKit 直接生成中文字幕。当前推荐流程是：

1. 从视频生成英文 `.en.srt`。
2. 用 OpenAI-compatible API 翻译英文 SRT，或打开在线编辑器逐条翻译/修改已有字幕。
3. 生成 `zh-Hans` SRT 时会做简体中文规范化。
4. 在页面截取预览帧，调整字体大小和字幕位置。
5. 选择外挂字幕或硬烧录到视频内部。

这个流程把“语音识别”和“翻译质量控制”拆开，避免 Whisper 中文直出导致繁体字和机翻质量问题。

## 架构

- `video_tool/transcriber.py`：调用 WhisperKit 生成 SRT。英文字幕使用 `transcribe --language en`。
- `video_tool/translator.py`：调用 OpenAI-compatible `/chat/completions` 接口翻译字幕文本。
- `video_tool/srt.py`：解析、写入、手动翻译和双语 SRT 导出。
- `video_tool/processor.py`：ffmpeg 预览、外挂字幕复制、硬字幕烧录；预览和硬烧录共用同一套字幕样式。
- `video_tool/web.py`：本地 Web UI、任务队列、文件选择、预览帧和关闭服务。
- `video_tool/cli.py`：命令行入口。
- `docs/design-system.md`：Web 工作台的颜色、间距、交互和响应式设计约束。

## 离线运行前提

字幕生成依赖本机 `whisperkit-cli`。硬字幕预览/烧录依赖支持 `subtitles`/`libass` 的 `ffmpeg`。

请确保 `ffmpeg` 可从 `PATH` 使用。如果安装在其他位置，运行前设置：

```bash
export FFMPEG_BIN=/path/to/ffmpeg
```

API 翻译不是离线能力。页面保留 `base_url`、`api_key`、`model` 输入，可指向 OpenAI 或本地 OpenAI-compatible 服务；手动编辑路径不调用任何 API。

## Web UI（一键启动）

### 普通用户：双击启动

在 macOS Finder 中双击项目根目录里的 `Barbara-Video-Subtitle-Studio.command`。启动器会自动选择项目自带的 Python 虚拟环境（如果存在），否则使用系统 Python，并打开本地工作台。

本分支已经附带编译好的 React 前端，因此普通用户不需要安装 Node.js 或 npm。启动器会在缺少 `ffmpeg` 或 `whisperkit-cli` 时给出清晰提示；字幕生成、预览和视频导出分别需要这些工具。

如果 macOS 第一次阻止打开，请右键该文件并选择“打开”。终端窗口请保持打开，关闭服务时可以点击页面右上角的 `Close Service`。

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
2. `Translate English SRT`：选择 `.en.srt` 后，可用 API 翻译生成 `视频名.zh-Hans.srt`，也可打开手动表格逐条填写中文。
3. `Preview and Finalize`：选择视频和字幕，调整字体大小、字幕位置，截取预览帧；确认后选择 `Hard burn into video` 或 `External sidecar subtitle`。
4. `在线编辑已有字幕`：选择任意 `.srt`，在线修改文本并保留原序号和时间轴，可覆盖保存或另存。

所有生成文件统一存入以初始视频名称命名的文件夹。例如选择 `/Videos/demo.mp4` 后，英文字幕、翻译字幕和输出视频都会写入 `/Videos/demo/`。任务完成或失败后，页面顶部会实时更新提示。

字幕位置参数是“距离底部的百分比”。例如 720p 视频里 `10%` 会换算成 `MarginV=72`。预览帧和硬烧录使用同一套 ffmpeg filter，因此页面看到的字幕位置和最终视频一致。

停止服务：页面右上角点击 `Close Service`，会关闭当前页面并停止本地 Python 监听服务。也可以在终端按 `Ctrl+C`。

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

## 当前边界

- 软字幕可以通过重新封装替换；硬字幕已经是画面像素，不能无损剥离。
- Web UI 的任务状态保存在内存里，重启服务后会清空。
- `burn` 模式会重新编码视频；`external` 模式只复制字幕文件，不改视频文件。
- `zh-Hans` 会强制规范化为简体中文，避免翻译或识别结果混入繁体字。
