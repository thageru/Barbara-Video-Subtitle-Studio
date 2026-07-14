import {
  AlertTriangle,
  Captions,
  CheckCircle2,
  ChevronDown,
  Eye,
  FileText,
  FileVideo,
  Film,
  FolderOpen,
  Infinity as InfinityIcon,
  Languages,
  ListChecks,
  LoaderCircle,
  Menu,
  Pause,
  PencilLine,
  Play,
  Power,
  WandSparkles,
  X,
  type LucideIcon,
} from 'lucide-react'
import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react'

const BG_VIDEO =
  'https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260511_230229_7c9bc431-46cf-489a-948d-e8144d8eb5d4.mp4'

type ViewId = 'generate' | 'translate' | 'finalize' | 'edit' | 'jobs'
type UiLanguage = 'zh' | 'en'
type Notice = { kind: 'success' | 'error' | 'info'; message: string } | null

type Job = {
  id: number
  status: 'queued' | 'running' | 'done' | 'failed'
  action: string
  mode: string
  languages: string
  video_path: string
  subtitle_path: string
  output_path: string
  details: string
  error: string
}

type GenerateForm = {
  video_path: string
  subtitle_dir: string
  subtitle_name: string
  model: string
}

type TranslateForm = {
  source_srt: string
  output_srt: string
  target_language: string
  base_url: string
  api_key: string
  model: string
  chunk_size: string
  glossary: string
}

type FinalizeForm = {
  video_path: string
  subtitle_path: string
  mode: string
  target_language: string
  font_size: string
  subtitle_y: string
  preview_time: string
  output_video: string
}

const copy = {
  zh: {
    brand: 'Barbara 视频字幕工作台',
    service: '本地服务在线',
    language: 'English',
    shutdown: '关闭服务',
    eyebrow: 'LOCAL SUBTITLE WORKFLOW',
    heroTitle: '从语音识别到最终视频，保持一个清晰流程。',
    heroBody: '生成英文字幕、翻译简体中文、在线校对并预览输出。视频文件只传递本地路径，不会上传到网页。',
    start: '开始生成',
    openEditor: '打开编辑器',
    pause: '暂停背景视频',
    play: '播放背景视频',
    remoteVideoFailed: '背景视频不可用，已切换到静态背景。',
    views: {
      generate: '生成字幕',
      translate: '翻译字幕',
      finalize: '预览输出',
      edit: '在线编辑',
      jobs: '任务状态',
    },
    descriptions: {
      generate: '先从英文音轨生成时间轴准确的 .en.srt。',
      translate: '通过 OpenAI-compatible 端点翻译为简体中文。',
      finalize: '预览字幕位置，然后输出硬字幕视频或外挂字幕。',
      edit: '打开已有 SRT，保留序号和时间轴进行逐条校对。',
      jobs: '查看后台任务的运行、完成和失败状态。',
    },
    chooseVideo: '选择视频',
    chooseFolder: '选择目录',
    chooseSubtitle: '选择字幕',
    videoFile: '视频文件',
    outputRoot: '输出根目录',
    subtitleName: '字幕基础文件名',
    whisperModel: 'WhisperKit 模型',
    generateAction: '生成英文 SRT',
    sourceSrt: '英文 SRT',
    outputSrt: '中文输出 SRT',
    targetLanguage: '目标语言',
    baseUrl: '接口地址 Base URL',
    apiKey: 'API Key',
    model: '模型',
    batchSize: '批次大小',
    glossary: '术语表 / 翻译说明',
    translateAction: '开始 AI 翻译',
    manualEditor: '手动翻译表格',
    subtitleFile: '字幕文件',
    outputMode: '输出方式',
    fontSize: '字体大小',
    subtitleY: '距底部百分比',
    previewTime: '预览时间点（秒）',
    outputPath: '输出视频 / 字幕路径',
    previewAction: '截取预览帧',
    finalizeAction: '开始输出',
    editAction: '打开在线编辑器',
    noJobs: '暂无任务。',
    working: '处理中...',
    jobStarted: (id: number) => `任务 ${id} 已开始。`,
    jobDone: (id: number) => `任务 ${id} 已完成。`,
    jobFailed: (id: number, error: string) => `任务 ${id} 失败：${error}`,
    previewFailed: '预览失败',
    requiredPath: '请先选择所需文件。',
    status: { queued: '排队中', running: '运行中', done: '完成', failed: '失败' },
  },
  en: {
    brand: 'Barbara Video Subtitle Studio',
    service: 'Local service online',
    language: '中文',
    shutdown: 'Close service',
    eyebrow: 'LOCAL SUBTITLE WORKFLOW',
    heroTitle: 'Move from speech recognition to final video in one focused flow.',
    heroBody: 'Generate English timing, translate to Simplified Chinese, review online, preview styling, and export. Local media paths stay on your machine.',
    start: 'Start generating',
    openEditor: 'Open editor',
    pause: 'Pause background video',
    play: 'Play background video',
    remoteVideoFailed: 'Background video is unavailable. A static fallback is active.',
    views: {
      generate: 'Generate',
      translate: 'Translate',
      finalize: 'Preview & export',
      edit: 'Edit',
      jobs: 'Jobs',
    },
    descriptions: {
      generate: 'Create a timing-accurate English .en.srt from the source audio.',
      translate: 'Translate through an OpenAI-compatible endpoint into Simplified Chinese.',
      finalize: 'Preview subtitle placement, then export hard-burned video or a sidecar file.',
      edit: 'Review an existing SRT line by line without changing indexes or timing.',
      jobs: 'Track queued, running, completed, and failed background jobs.',
    },
    chooseVideo: 'Choose video',
    chooseFolder: 'Choose folder',
    chooseSubtitle: 'Choose subtitle',
    videoFile: 'Video file',
    outputRoot: 'Output root directory',
    subtitleName: 'Subtitle base name',
    whisperModel: 'WhisperKit model',
    generateAction: 'Generate English SRT',
    sourceSrt: 'English SRT',
    outputSrt: 'Translated output SRT',
    targetLanguage: 'Target language',
    baseUrl: 'Base URL',
    apiKey: 'API Key',
    model: 'Model',
    batchSize: 'Batch size',
    glossary: 'Glossary / translation notes',
    translateAction: 'Start AI translation',
    manualEditor: 'Manual translation table',
    subtitleFile: 'Subtitle file',
    outputMode: 'Output mode',
    fontSize: 'Font size',
    subtitleY: 'Bottom margin percent',
    previewTime: 'Preview timestamp (seconds)',
    outputPath: 'Output video / subtitle path',
    previewAction: 'Capture preview frame',
    finalizeAction: 'Start export',
    editAction: 'Open online editor',
    noJobs: 'No jobs yet.',
    working: 'Working...',
    jobStarted: (id: number) => `Job ${id} started.`,
    jobDone: (id: number) => `Job ${id} completed.`,
    jobFailed: (id: number, error: string) => `Job ${id} failed: ${error}`,
    previewFailed: 'Preview failed',
    requiredPath: 'Choose the required files first.',
    status: { queued: 'queued', running: 'running', done: 'done', failed: 'failed' },
  },
} as const

const viewMeta: Array<{ id: ViewId; icon: LucideIcon }> = [
  { id: 'generate', icon: Captions },
  { id: 'translate', icon: Languages },
  { id: 'finalize', icon: Film },
  { id: 'edit', icon: PencilLine },
  { id: 'jobs', icon: ListChecks },
]

function splitPath(path: string) {
  const normalized = path.split('\\').join('/')
  const slash = normalized.lastIndexOf('/')
  const dir = slash >= 0 ? normalized.slice(0, slash) : ''
  const file = slash >= 0 ? normalized.slice(slash + 1) : normalized
  const dot = file.lastIndexOf('.')
  const stem = dot > 0 ? file.slice(0, dot) : file
  return { dir, file, stem }
}

function Field({ label, required, children }: { label: string; required?: boolean; children: ReactNode }) {
  return (
    <label className="grid min-w-0 gap-2 text-sm font-medium text-white/78">
      <span>
        {label}
        {required ? <span className="ml-1 text-accent" aria-hidden="true">*</span> : null}
      </span>
      {children}
    </label>
  )
}

function PathField({
  label,
  value,
  placeholder,
  buttonLabel,
  icon: Icon,
  required,
  busy,
  onChange,
  onChoose,
}: {
  label: string
  value: string
  placeholder: string
  buttonLabel: string
  icon: LucideIcon
  required?: boolean
  busy?: boolean
  onChange: (value: string) => void
  onChoose: () => void
}) {
  return (
    <Field label={label} required={required}>
      <div className="grid min-w-0 gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
        <input
          className="field-control"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          required={required}
        />
        <button
          type="button"
          onClick={onChoose}
          disabled={busy}
          className="liquid-glass inline-flex min-h-11 items-center justify-center gap-2 rounded-xl px-4 text-sm font-medium text-white transition-colors hover:bg-white/10 disabled:cursor-wait disabled:opacity-50"
        >
          {busy ? <LoaderCircle size={16} className="animate-spin" /> : <Icon size={16} strokeWidth={1.7} />}
          {buttonLabel}
        </button>
      </div>
    </Field>
  )
}

function PrimaryButton({ busy, children }: { busy?: boolean; children: ReactNode }) {
  return (
    <button
      type="submit"
      disabled={busy}
      className="inline-flex min-h-11 items-center justify-center gap-2 rounded-full bg-white px-6 text-sm font-semibold text-black transition-colors hover:bg-white/90 disabled:cursor-wait disabled:opacity-60"
    >
      {busy ? <LoaderCircle size={17} className="animate-spin" /> : <WandSparkles size={17} strokeWidth={1.8} />}
      {children}
    </button>
  )
}

export default function App() {
  const [language, setLanguage] = useState<UiLanguage>(() => (localStorage.getItem('barbara-ui-language') === 'en' ? 'en' : 'zh'))
  const [activeView, setActiveView] = useState<ViewId>('generate')
  const [menuOpen, setMenuOpen] = useState(false)
  const [videoPaused, setVideoPaused] = useState(false)
  const [videoFailed, setVideoFailed] = useState(false)
  const [notice, setNotice] = useState<Notice>(null)
  const [busyKey, setBusyKey] = useState('')
  const [jobs, setJobs] = useState<Job[]>([])
  const [previewUrl, setPreviewUrl] = useState('')
  const videoRef = useRef<HTMLVideoElement>(null)
  const knownStatuses = useRef(new Map<number, Job['status']>())

  const [generateForm, setGenerateForm] = useState<GenerateForm>({ video_path: '', subtitle_dir: '', subtitle_name: '', model: 'small' })
  const [translateForm, setTranslateForm] = useState<TranslateForm>({
    source_srt: '',
    output_srt: '',
    target_language: 'zh-Hans',
    base_url: '',
    api_key: '',
    model: 'gpt-4.1-mini',
    chunk_size: '20',
    glossary: '',
  })
  const [finalizeForm, setFinalizeForm] = useState<FinalizeForm>({
    video_path: '',
    subtitle_path: '',
    mode: 'burn',
    target_language: 'zh-Hans',
    font_size: '22',
    subtitle_y: '2',
    preview_time: '10',
    output_video: '',
  })
  const [editSubtitle, setEditSubtitle] = useState('')

  const text = copy[language]
  const activeMeta = useMemo(() => viewMeta.find((item) => item.id === activeView) ?? viewMeta[0], [activeView])
  const ActiveIcon = activeMeta.icon

  useEffect(() => {
    localStorage.setItem('barbara-ui-language', language)
    document.documentElement.lang = language === 'zh' ? 'zh-CN' : 'en'
  }, [language])

  useEffect(() => {
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
    if (reducedMotion.matches) setVideoPaused(true)
  }, [])

  useEffect(() => {
    const video = videoRef.current
    if (!video || videoFailed) return
    if (videoPaused) video.pause()
    else void video.play().catch(() => setVideoPaused(true))
  }, [videoPaused, videoFailed])

  useEffect(() => {
    if (!notice) return
    const timeout = window.setTimeout(() => setNotice(null), 4800)
    return () => window.clearTimeout(timeout)
  }, [notice])

  const loadJobs = useCallback(async () => {
    try {
      const response = await fetch('/jobs.json', { headers: { Accept: 'application/json' } })
      if (!response.ok) return
      const nextJobs = (await response.json()) as Job[]
      nextJobs.forEach((job) => {
        const previous = knownStatuses.current.get(job.id)
        if (previous && previous !== job.status && job.status === 'done') {
          setNotice({ kind: 'success', message: copy[language].jobDone(job.id) })
        }
        if (previous && previous !== job.status && job.status === 'failed') {
          setNotice({ kind: 'error', message: copy[language].jobFailed(job.id, job.error || '') })
        }
        knownStatuses.current.set(job.id, job.status)
      })
      setJobs(nextJobs)
    } catch {
      // The polling loop will retry when the local service becomes available again.
    }
  }, [language])

  useEffect(() => {
    void loadJobs()
    const timer = window.setInterval(() => void loadJobs(), 3000)
    return () => window.clearInterval(timer)
  }, [loadJobs])

  const choosePath = async (endpoint: string, key: string, onSelected: (path: string) => void) => {
    setBusyKey(key)
    try {
      const response = await fetch(endpoint, { headers: { Accept: 'application/json' } })
      const payload = (await response.json()) as { ok?: boolean; path?: string; error?: string }
      if (!payload.ok || !payload.path) throw new Error(payload.error || text.requiredPath)
      onSelected(payload.path)
    } catch (error) {
      setNotice({ kind: 'error', message: String(error) })
    } finally {
      setBusyKey('')
    }
  }

  const setVideoDefaults = (path: string) => {
    const parts = splitPath(path)
    setGenerateForm((current) => ({
      ...current,
      video_path: path,
      subtitle_dir: current.subtitle_dir || (parts.dir ? `${parts.dir}/${parts.stem}` : parts.stem),
      subtitle_name: current.subtitle_name || parts.stem,
    }))
    setFinalizeForm((current) => ({ ...current, video_path: current.video_path || path }))
  }

  const setSrtDefaults = (path: string) => {
    const target = path.endsWith('.en.srt')
      ? `${path.slice(0, -7)}.zh-Hans.srt`
      : path.endsWith('.srt')
        ? `${path.slice(0, -4)}.zh-Hans.srt`
        : `${path}.zh-Hans.srt`
    setTranslateForm((current) => ({ ...current, source_srt: path, output_srt: current.output_srt || target }))
    setFinalizeForm((current) => ({ ...current, subtitle_path: current.subtitle_path || target }))
  }

  const updateFinalOutput = (updates: Partial<FinalizeForm>) => {
    setFinalizeForm((current) => {
      const next = { ...current, ...updates }
      if (!next.video_path) return next
      const video = splitPath(next.video_path)
      const suffix = next.mode === 'burn' ? '.zh-Hans.hardsub.mp4' : '.zh-Hans.srt'
      return { ...next, output_video: `${video.dir ? `${video.dir}/` : ''}${video.stem}/${video.stem}${suffix}` }
    })
  }

  const submitJob = async (endpoint: string, payload: Record<string, string>, key: string) => {
    setBusyKey(key)
    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { Accept: 'application/json', 'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8' },
        body: new URLSearchParams(payload),
      })
      const result = (await response.json()) as { ok?: boolean; job_id?: number; error?: string }
      if (!response.ok || !result.ok || !result.job_id) throw new Error(result.error || `HTTP ${response.status}`)
      knownStatuses.current.set(result.job_id, 'queued')
      setNotice({ kind: 'info', message: text.jobStarted(result.job_id) })
      await loadJobs()
    } catch (error) {
      setNotice({ kind: 'error', message: String(error) })
    } finally {
      setBusyKey('')
    }
  }

  const previewFrame = async () => {
    if (!finalizeForm.video_path || !finalizeForm.subtitle_path) {
      setNotice({ kind: 'error', message: text.requiredPath })
      return
    }
    setBusyKey('preview')
    setPreviewUrl('')
    try {
      const response = await fetch('/preview-frame', {
        method: 'POST',
        headers: { Accept: 'application/json', 'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8' },
        body: new URLSearchParams(finalizeForm),
      })
      const result = (await response.json()) as { ok?: boolean; url?: string; error?: string }
      if (!result.ok || !result.url) throw new Error(result.error || text.previewFailed)
      setPreviewUrl(`${result.url}?t=${Date.now()}`)
    } catch (error) {
      setNotice({ kind: 'error', message: String(error) })
    } finally {
      setBusyKey('')
    }
  }

  const openEditor = (source: string, target?: string, prefill = false) => {
    if (!source) {
      setNotice({ kind: 'error', message: text.requiredPath })
      return
    }
    const params = new URLSearchParams({ source, target: target || source })
    if (prefill) params.set('prefill', '1')
    window.location.href = `/edit?${params.toString()}`
  }

  const shutdown = async () => {
    if (!window.confirm(language === 'zh' ? '现在关闭本地服务吗？' : 'Close the local service now?')) return
    await fetch('/shutdown', { method: 'POST', headers: { Accept: 'application/json' } })
    setNotice({ kind: 'info', message: language === 'zh' ? '本地服务已关闭。' : 'The local service has stopped.' })
  }

  const selectView = (view: ViewId) => {
    setActiveView(view)
    setMenuOpen(false)
  }

  const renderActiveView = () => {
    if (activeView === 'generate') {
      return (
        <form
          className="grid gap-4"
          onSubmit={(event: FormEvent) => {
            event.preventDefault()
            void submitJob('/generate-english', generateForm, 'generate')
          }}
        >
          <PathField
            label={text.videoFile}
            value={generateForm.video_path}
            placeholder={language === 'zh' ? '选择本地视频文件' : 'Choose a local video file'}
            buttonLabel={text.chooseVideo}
            icon={FileVideo}
            required
            busy={busyKey === 'generate-video'}
            onChange={setVideoDefaults}
            onChoose={() => void choosePath('/choose-file?purpose=video', 'generate-video', setVideoDefaults)}
          />
          <div className="grid gap-4 md:grid-cols-2">
            <PathField
              label={text.outputRoot}
              value={generateForm.subtitle_dir}
              placeholder={language === 'zh' ? '默认创建 视频名/ 文件夹' : 'Creates a video-name folder'}
              buttonLabel={text.chooseFolder}
              icon={FolderOpen}
              busy={busyKey === 'generate-folder'}
              onChange={(value) => setGenerateForm((current) => ({ ...current, subtitle_dir: value }))}
              onChoose={() =>
                void choosePath('/choose-directory', 'generate-folder', (path) =>
                  setGenerateForm((current) => ({ ...current, subtitle_dir: path })),
                )
              }
            />
            <Field label={text.subtitleName}>
              <input
                className="field-control"
                value={generateForm.subtitle_name}
                onChange={(event) => setGenerateForm((current) => ({ ...current, subtitle_name: event.target.value }))}
                placeholder={language === 'zh' ? '默认使用视频文件名' : 'Defaults to video file name'}
              />
            </Field>
          </div>
          <Field label={text.whisperModel}>
            <input
              className="field-control"
              value={generateForm.model}
              onChange={(event) => setGenerateForm((current) => ({ ...current, model: event.target.value }))}
            />
          </Field>
          <div className="flex flex-wrap items-center gap-3 pt-2">
            <PrimaryButton busy={busyKey === 'generate'}>{busyKey === 'generate' ? text.working : text.generateAction}</PrimaryButton>
            <span className="text-xs text-white/52">{language === 'zh' ? '输出：字幕名.en.srt' : 'Output: subtitle-name.en.srt'}</span>
          </div>
        </form>
      )
    }

    if (activeView === 'translate') {
      return (
        <form
          className="grid gap-4"
          onSubmit={(event) => {
            event.preventDefault()
            void submitJob('/translate-ai', translateForm, 'translate')
          }}
        >
          <PathField
            label={text.sourceSrt}
            value={translateForm.source_srt}
            placeholder={language === 'zh' ? '选择 .en.srt' : 'Choose .en.srt'}
            buttonLabel={text.chooseSubtitle}
            icon={FileText}
            required
            busy={busyKey === 'translate-source'}
            onChange={setSrtDefaults}
            onChoose={() => void choosePath('/choose-file?purpose=subtitle', 'translate-source', setSrtDefaults)}
          />
          <div className="grid gap-4 md:grid-cols-2">
            <Field label={text.outputSrt} required>
              <input
                className="field-control"
                value={translateForm.output_srt}
                onChange={(event) => setTranslateForm((current) => ({ ...current, output_srt: event.target.value }))}
                required
              />
            </Field>
            <Field label={text.targetLanguage}>
              <select
                className="field-control"
                value={translateForm.target_language}
                onChange={(event) => setTranslateForm((current) => ({ ...current, target_language: event.target.value }))}
              >
                <option value="zh-Hans">zh-Hans - {language === 'zh' ? '简体中文' : 'Simplified Chinese'}</option>
                <option value="en">en - English</option>
              </select>
            </Field>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <Field label={text.baseUrl}>
              <input
                className="field-control"
                type="url"
                inputMode="url"
                value={translateForm.base_url}
                onChange={(event) => setTranslateForm((current) => ({ ...current, base_url: event.target.value }))}
                placeholder="https://api.openai.com/v1"
              />
            </Field>
            <Field label={text.apiKey}>
              <input
                className="field-control"
                type="password"
                autoComplete="off"
                value={translateForm.api_key}
                onChange={(event) => setTranslateForm((current) => ({ ...current, api_key: event.target.value }))}
                placeholder={language === 'zh' ? '本地端点可留空' : 'Optional for local endpoints'}
              />
            </Field>
            <Field label={text.model}>
              <input
                className="field-control"
                value={translateForm.model}
                onChange={(event) => setTranslateForm((current) => ({ ...current, model: event.target.value }))}
              />
            </Field>
            <Field label={text.batchSize}>
              <input
                className="field-control"
                type="number"
                min="5"
                max="50"
                inputMode="numeric"
                value={translateForm.chunk_size}
                onChange={(event) => setTranslateForm((current) => ({ ...current, chunk_size: event.target.value }))}
              />
            </Field>
          </div>
          <Field label={text.glossary}>
            <textarea
              className="field-control min-h-24 resize-y"
              value={translateForm.glossary}
              onChange={(event) => setTranslateForm((current) => ({ ...current, glossary: event.target.value }))}
              placeholder={language === 'zh' ? '例如：PYP=小学项目，transdisciplinary=超学科' : 'Example: PYP=Primary Years Programme'}
            />
          </Field>
          <div className="flex flex-wrap gap-3 pt-2">
            <PrimaryButton busy={busyKey === 'translate'}>{busyKey === 'translate' ? text.working : text.translateAction}</PrimaryButton>
            <button
              type="button"
              onClick={() => openEditor(translateForm.source_srt, translateForm.output_srt)}
              className="liquid-glass min-h-11 rounded-full px-6 text-sm font-medium text-white transition-colors hover:bg-white/10"
            >
              {text.manualEditor}
            </button>
          </div>
        </form>
      )
    }

    if (activeView === 'finalize') {
      return (
        <div className="grid gap-5">
          <form
            className="grid gap-4"
            onSubmit={(event) => {
              event.preventDefault()
              void submitJob('/finalize', finalizeForm, 'finalize')
            }}
          >
            <PathField
              label={text.videoFile}
              value={finalizeForm.video_path}
              placeholder={language === 'zh' ? '选择本地视频文件' : 'Choose a local video file'}
              buttonLabel={text.chooseVideo}
              icon={FileVideo}
              required
              busy={busyKey === 'final-video'}
              onChange={(value) => updateFinalOutput({ video_path: value })}
              onChoose={() => void choosePath('/choose-file?purpose=video', 'final-video', (path) => updateFinalOutput({ video_path: path }))}
            />
            <PathField
              label={text.subtitleFile}
              value={finalizeForm.subtitle_path}
              placeholder={language === 'zh' ? '选择翻译后的 .srt' : 'Choose translated .srt'}
              buttonLabel={text.chooseSubtitle}
              icon={FileText}
              required
              busy={busyKey === 'final-subtitle'}
              onChange={(value) => updateFinalOutput({ subtitle_path: value })}
              onChoose={() =>
                void choosePath('/choose-file?purpose=subtitle', 'final-subtitle', (path) => updateFinalOutput({ subtitle_path: path }))
              }
            />
            <div className="grid gap-4 md:grid-cols-2">
              <Field label={text.outputMode}>
                <select className="field-control" value={finalizeForm.mode} onChange={(event) => updateFinalOutput({ mode: event.target.value })}>
                  <option value="burn">{language === 'zh' ? '硬字幕烧录进视频' : 'Hard burn into video'}</option>
                  <option value="external">{language === 'zh' ? '外挂字幕文件' : 'External sidecar subtitle'}</option>
                </select>
              </Field>
              <Field label={text.targetLanguage}>
                <select
                  className="field-control"
                  value={finalizeForm.target_language}
                  onChange={(event) => updateFinalOutput({ target_language: event.target.value })}
                >
                  <option value="zh-Hans">zh-Hans - {language === 'zh' ? '简体中文' : 'Simplified Chinese'}</option>
                  <option value="en">en - English</option>
                </select>
              </Field>
              <Field label={text.fontSize}>
                <input
                  className="field-control"
                  type="number"
                  min="8"
                  max="128"
                  inputMode="numeric"
                  value={finalizeForm.font_size}
                  onChange={(event) => updateFinalOutput({ font_size: event.target.value })}
                />
              </Field>
              <Field label={`${text.subtitleY}: ${finalizeForm.subtitle_y}%`}>
                <input
                  className="h-11 w-full accent-emerald-200"
                  type="range"
                  min="0"
                  max="100"
                  value={finalizeForm.subtitle_y}
                  onChange={(event) => updateFinalOutput({ subtitle_y: event.target.value })}
                />
              </Field>
              <Field label={text.previewTime}>
                <input
                  className="field-control"
                  type="number"
                  min="0"
                  step="0.1"
                  inputMode="decimal"
                  value={finalizeForm.preview_time}
                  onChange={(event) => updateFinalOutput({ preview_time: event.target.value })}
                />
              </Field>
              <Field label={text.outputPath}>
                <input
                  className="field-control"
                  value={finalizeForm.output_video}
                  onChange={(event) => setFinalizeForm((current) => ({ ...current, output_video: event.target.value }))}
                />
              </Field>
            </div>
            <div className="flex flex-wrap gap-3 pt-2">
              <button
                type="button"
                onClick={() => void previewFrame()}
                disabled={busyKey === 'preview'}
                className="liquid-glass inline-flex min-h-11 items-center gap-2 rounded-full px-6 text-sm font-medium text-white transition-colors hover:bg-white/10 disabled:opacity-50"
              >
                {busyKey === 'preview' ? <LoaderCircle size={17} className="animate-spin" /> : <Eye size={17} />}
                {text.previewAction}
              </button>
              <PrimaryButton busy={busyKey === 'finalize'}>{busyKey === 'finalize' ? text.working : text.finalizeAction}</PrimaryButton>
            </div>
          </form>
          {previewUrl ? (
            <figure className="overflow-hidden rounded-2xl border border-white/15 bg-black/25">
              <img src={previewUrl} alt={language === 'zh' ? '字幕预览帧' : 'Subtitle preview frame'} className="block w-full" />
            </figure>
          ) : null}
        </div>
      )
    }

    if (activeView === 'edit') {
      return (
        <div className="grid gap-5">
          <PathField
            label={text.subtitleFile}
            value={editSubtitle}
            placeholder={language === 'zh' ? '选择要编辑的 .srt' : 'Choose an existing .srt'}
            buttonLabel={text.chooseSubtitle}
            icon={FileText}
            required
            busy={busyKey === 'edit-subtitle'}
            onChange={setEditSubtitle}
            onChoose={() => void choosePath('/choose-file?purpose=subtitle', 'edit-subtitle', setEditSubtitle)}
          />
          <div className="rounded-2xl border border-white/10 bg-black/15 p-4 text-sm leading-6 text-white/62">
            {language === 'zh'
              ? '编辑器会读取现有 SRT 文本并预填每一条字幕。保存时保留原序号和时间轴，zh-Hans 会自动规范为简体中文。'
              : 'The editor prefills every existing subtitle line. Saving preserves indexes and timing, and zh-Hans output is normalized to Simplified Chinese.'}
          </div>
          <button
            type="button"
            onClick={() => openEditor(editSubtitle, editSubtitle, true)}
            className="inline-flex min-h-11 w-fit items-center gap-2 rounded-full bg-white px-6 text-sm font-semibold text-black transition-colors hover:bg-white/90"
          >
            <PencilLine size={17} />
            {text.editAction}
          </button>
        </div>
      )
    }

    return (
      <div className="grid gap-1">
        {jobs.length ? (
          jobs.map((job) => {
            const StatusIcon = job.status === 'done' ? CheckCircle2 : job.status === 'failed' ? AlertTriangle : LoaderCircle
            return (
              <div key={job.id} className="grid gap-3 border-b border-white/10 py-4 last:border-b-0 sm:grid-cols-[90px_1fr_auto] sm:items-start">
                <div className="flex items-center gap-2 text-xs font-medium text-white/55">
                  <StatusIcon size={16} className={job.status === 'running' ? 'animate-spin text-accent' : job.status === 'failed' ? 'text-red-300' : 'text-accent'} />
                  #{job.id}
                </div>
                <div className="min-w-0">
                  <p className="m-0 text-sm font-medium text-white">{job.action}</p>
                  <p className="mt-1 break-all text-xs leading-5 text-white/48">{job.output_path || job.video_path || job.subtitle_path}</p>
                  {job.error ? <p className="mt-2 break-words text-xs text-red-200">{job.error}</p> : null}
                </div>
                <span className="w-fit rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-white/72">{text.status[job.status]}</span>
              </div>
            )
          })
        ) : (
          <div className="grid min-h-48 place-items-center text-sm text-white/52">{text.noJobs}</div>
        )}
      </div>
    )
  }

  return (
    <div className="relative min-h-dvh w-full overflow-x-hidden bg-[#0b1114] text-white lg:h-screen lg:overflow-hidden">
      {!videoFailed ? (
        <video
          ref={videoRef}
          className="fixed inset-0 h-full w-full object-cover"
          autoPlay={!videoPaused}
          muted
          loop
          playsInline
          preload="metadata"
          src={BG_VIDEO}
          onError={() => setVideoFailed(true)}
          aria-hidden="true"
        />
      ) : null}
      <div className="fixed inset-0 bg-black/45" aria-hidden="true" />
      <div className="fixed inset-0 bg-[linear-gradient(90deg,rgba(3,8,10,0.72)_0%,rgba(3,8,10,0.38)_45%,rgba(3,8,10,0.58)_100%)]" aria-hidden="true" />

      <header className="fixed left-0 right-0 top-0 z-30 flex items-center justify-between px-4 py-4 sm:px-8 sm:py-5">
        <button type="button" onClick={() => selectView('generate')} className="flex min-h-11 items-center gap-2 text-base font-medium text-white" aria-label={text.brand}>
          <InfinityIcon size={23} strokeWidth={1.5} />
          <span className="hidden sm:inline">Barbara</span>
        </button>

        <nav className="liquid-glass hidden items-center gap-1 rounded-xl px-2 py-2 md:flex" aria-label={language === 'zh' ? '字幕工作流' : 'Subtitle workflow'}>
          {viewMeta.map(({ id, icon: Icon }) => (
            <button
              key={id}
              type="button"
              onClick={() => selectView(id)}
              aria-current={activeView === id ? 'page' : undefined}
              className={`flex min-h-9 items-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition-colors ${
                activeView === id ? 'bg-white/15 text-white' : 'text-white/65 hover:text-white'
              }`}
            >
              <Icon size={14} strokeWidth={1.6} />
              {text.views[id]}
            </button>
          ))}
        </nav>

        <div className="hidden items-center gap-3 md:flex">
          <span className="text-xs text-white/55">{text.service}</span>
          <button type="button" onClick={() => setLanguage((current) => (current === 'zh' ? 'en' : 'zh'))} className="liquid-glass min-h-11 rounded-full px-4 text-sm font-medium text-white transition-colors hover:bg-white/10">
            {text.language}
          </button>
          <button type="button" onClick={() => void shutdown()} className="inline-flex min-h-11 items-center gap-2 rounded-full bg-white px-4 text-sm font-medium text-black transition-colors hover:bg-white/90">
            <Power size={16} />
            {text.shutdown}
          </button>
        </div>

        <button
          type="button"
          onClick={() => setMenuOpen((current) => !current)}
          className="liquid-glass grid min-h-11 min-w-11 place-items-center rounded-lg text-white md:hidden"
          aria-label={menuOpen ? 'Close menu' : 'Open menu'}
          aria-expanded={menuOpen}
        >
          {menuOpen ? <X size={19} /> : <Menu size={19} />}
        </button>
      </header>

      {menuOpen ? (
        <div className="liquid-glass-strong fixed left-4 right-4 top-[76px] z-40 grid gap-1 rounded-2xl p-4 md:hidden">
          {viewMeta.map(({ id, icon: Icon }) => (
            <button
              key={id}
              type="button"
              onClick={() => selectView(id)}
              className={`flex min-h-11 items-center justify-between rounded-xl px-4 text-sm ${activeView === id ? 'bg-white/12 text-white' : 'text-white/68'}`}
            >
              <span className="flex items-center gap-2"><Icon size={16} />{text.views[id]}</span>
              {activeView === id ? <ChevronDown size={15} /> : null}
            </button>
          ))}
          <div className="mt-2 grid grid-cols-2 gap-2 border-t border-white/10 pt-3">
            <button type="button" onClick={() => setLanguage((current) => (current === 'zh' ? 'en' : 'zh'))} className="liquid-glass min-h-11 rounded-full text-sm font-medium text-white">{text.language}</button>
            <button type="button" onClick={() => void shutdown()} className="min-h-11 rounded-full bg-white text-sm font-medium text-black">{text.shutdown}</button>
          </div>
        </div>
      ) : null}

      <main className="relative z-20 mx-auto grid min-h-dvh w-full max-w-[1600px] gap-8 px-4 pb-8 pt-24 sm:px-8 lg:h-screen lg:grid-cols-[minmax(300px,0.8fr)_minmax(560px,1.2fr)] lg:items-end lg:gap-12 lg:px-12 lg:pb-10 lg:pt-28">
        <section className="flex max-w-xl flex-col justify-end pb-2 lg:pb-8">
          <p className="mb-3 text-xs font-medium tracking-[0.18em] text-accent/80">{text.eyebrow}</p>
          <h1 className="mb-4 text-4xl font-medium leading-[1.05] tracking-tight text-white sm:text-5xl lg:text-6xl">{text.heroTitle}</h1>
          <p className="mb-7 max-w-lg text-sm leading-6 text-white/65 sm:text-base">{text.heroBody}</p>
          <div className="flex flex-wrap items-center gap-3">
            <button type="button" onClick={() => selectView('generate')} className="min-h-11 rounded-full bg-white px-6 text-sm font-medium text-black transition-colors hover:bg-white/90 sm:px-7 sm:text-base">{text.start}</button>
            <button type="button" onClick={() => selectView('edit')} className="liquid-glass min-h-11 rounded-full px-6 text-sm font-medium text-white transition-colors hover:bg-white/10 sm:px-7 sm:text-base">{text.openEditor}</button>
            <button
              type="button"
              onClick={() => setVideoPaused((current) => !current)}
              className="liquid-glass grid min-h-11 min-w-11 place-items-center rounded-full text-white transition-colors hover:bg-white/10"
              aria-label={videoPaused ? text.play : text.pause}
              title={videoPaused ? text.play : text.pause}
            >
              {videoPaused ? <Play size={17} /> : <Pause size={17} />}
            </button>
          </div>
          {videoFailed ? <p className="mt-4 text-xs text-amber-100/75">{text.remoteVideoFailed}</p> : null}
        </section>

        <section className="liquid-glass-strong workspace-scrollbar max-h-[calc(100dvh-8rem)] min-h-[520px] overflow-y-auto rounded-3xl p-5 shadow-glass sm:p-7 lg:min-h-0 lg:self-stretch">
          <div className="mb-6 flex items-start justify-between gap-4 border-b border-white/10 pb-5">
            <div className="flex min-w-0 items-start gap-3">
              <span className="liquid-glass grid h-11 w-11 flex-none place-items-center rounded-xl text-accent"><ActiveIcon size={20} strokeWidth={1.6} /></span>
              <div className="min-w-0">
                <h2 className="m-0 text-xl font-medium text-white">{text.views[activeView]}</h2>
                <p className="mt-1 text-sm leading-5 text-white/52">{text.descriptions[activeView]}</p>
              </div>
            </div>
            {activeView !== 'jobs' && jobs.some((job) => job.status === 'running' || job.status === 'queued') ? (
              <button type="button" onClick={() => selectView('jobs')} className="liquid-glass flex min-h-11 flex-none items-center gap-2 rounded-full px-4 text-xs text-white/80">
                <LoaderCircle size={15} className="animate-spin text-accent" />
                {jobs.filter((job) => job.status === 'running' || job.status === 'queued').length}
              </button>
            ) : null}
          </div>
          {renderActiveView()}
        </section>
      </main>

      {notice ? (
        <div
          role={notice.kind === 'error' ? 'alert' : 'status'}
          aria-live={notice.kind === 'error' ? 'assertive' : 'polite'}
          className={`liquid-glass-strong fixed bottom-5 left-1/2 z-50 flex w-[min(92vw,520px)] -translate-x-1/2 items-start gap-3 rounded-2xl px-4 py-3 text-sm shadow-glass ${
            notice.kind === 'error' ? 'text-red-100' : notice.kind === 'success' ? 'text-emerald-100' : 'text-white'
          }`}
        >
          {notice.kind === 'error' ? <AlertTriangle size={18} className="mt-0.5 flex-none" /> : <CheckCircle2 size={18} className="mt-0.5 flex-none" />}
          <span className="min-w-0 break-words">{notice.message}</span>
          <button type="button" onClick={() => setNotice(null)} className="ml-auto grid h-8 w-8 flex-none place-items-center rounded-lg text-white/60 hover:bg-white/10 hover:text-white" aria-label="Dismiss notification"><X size={15} /></button>
        </div>
      ) : null}
    </div>
  )
}
