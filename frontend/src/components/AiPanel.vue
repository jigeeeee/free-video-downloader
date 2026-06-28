<script setup>
import { ref, watch } from "vue"

const props = defineProps({
  url: String,
  title: String,
})

const activeTab = ref(null) // 'summary' | 'subtitles' | 'mindmap' | 'ask'
const isLoading = ref(false)
const error = ref(null)

// ── Per-tab state ─────────────────────────────────────────────────
const summaryResult = ref(null)
const subtitleResult = ref(null)
const mindmapResult = ref(null)
const askQuestion = ref("")
const askAnswer = ref(null)
const askHistory = ref([])
const showAll = ref({})  // { lang: bool } — per language expand state

// Reset when URL changes
watch(() => props.url, () => {
  activeTab.value = null
  summaryResult.value = null
  subtitleResult.value = null
  mindmapResult.value = null
  askAnswer.value = null
  askHistory.value = []
  error.value = null
})

// ── Generic poll helper ───────────────────────────────────────────
async function pollUntil(endpoint, taskId) {
  for (let i = 0; i < 60; i++) {
    await new Promise(r => setTimeout(r, 2000))
    const res = await fetch(`/api/${endpoint}/${taskId}`)
    const data = await res.json()
    if (data.status === "done") return data.result
    if (data.status === "error") throw new Error(data.error || "AI task failed")
  }
  throw new Error("Timeout")
}

// ── Tab actions ───────────────────────────────────────────────────
async function loadSummary() {
  activeTab.value = "summary"
  if (summaryResult.value) return
  await runAi("summary", (r) => { summaryResult.value = r })
}

async function loadSubtitles() {
  activeTab.value = "subtitles"
  if (subtitleResult.value) return
  isLoading.value = true
  error.value = null
  try {
    // Only request Chinese languages
    const res = await fetch("/api/subtitles", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: props.url, languages: ["zh-Hans", "zh", "zh-CN"] }),
    })
    if (!res.ok) throw new Error((await res.json()).detail || "Subtitles failed")
    const { task_id } = await res.json()
    let result = await pollUntil("subtitles", task_id)

    // If no Chinese subtitles found, try English + auto-translate
    const chineseLangs = ["zh-Hans", "zh", "zh-CN", "zh-TW", "yue"]
    const hasChinese = (result.extracted || []).some(e =>
      chineseLangs.some(l => e.lang.startsWith(l))
    )
    if (!hasChinese && (result.extracted || []).length === 0) {
      // No subtitles at all — try English
      const enRes = await fetch("/api/subtitles", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: props.url, languages: ["en"] }),
      })
      if (enRes.ok) {
        const { task_id: enTid } = await enRes.json()
        const enResult = await pollUntil("subtitles", enTid)
        if (enResult.extracted?.length) {
          for (const entry of enResult.extracted) {
            try {
              const tres = await fetch("/api/translate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ text: entry.text || entry.text_preview, target_lang: "简体中文" }),
              })
              if (tres.ok) {
                const tdata = await tres.json()
                entry.text = tdata.translated_text
                entry.text_preview = tdata.translated_text.slice(0, 500)
                entry.lang = "zh"  // mark as Chinese
                entry.source = "auto-translated"
              }
            } catch (e) { /* skip */ }
          }
          result = enResult
        }
      }
    }

    // Remove any English-only entries that weren't translated
    if (result.extracted) {
      result.extracted = result.extracted.filter(e =>
        chineseLangs.some(l => e.lang.startsWith(l)) || e.source === "auto-translated"
      )
    }
    subtitleResult.value = result
  } catch (e) {
    error.value = e.message
    activeTab.value = null
  } finally {
    isLoading.value = false
  }
}

async function loadMindmap() {
  activeTab.value = "mindmap"
  if (mindmapResult.value) return
  await runAi("mindmap", (r) => { mindmapResult.value = r })
}

async function submitAsk() {
  const q = askQuestion.value.trim()
  if (!q) return
  activeTab.value = "ask"
  isLoading.value = true
  error.value = null
  try {
    const res = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: props.url,
        question: q,
        lang: "zh",
        history: askHistory.value,
      }),
    })
    if (!res.ok) throw new Error((await res.json()).detail || "Ask failed")
    const { task_id } = await res.json()
    const result = await pollUntil("ask", task_id)
    askAnswer.value = result
    askHistory.value.push({ question: q, answer: result.answer })
    askQuestion.value = ""
  } catch (e) {
    error.value = e.message
  } finally {
    isLoading.value = false
  }
}

async function runAi(endpoint, setter) {
  isLoading.value = true
  error.value = null
  try {
    const res = await fetch(`/api/${endpoint}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: props.url, lang: "zh" }),
    })
    if (!res.ok) throw new Error((await res.json()).detail || `${endpoint} failed`)
    const { task_id } = await res.json()
    const result = await pollUntil(endpoint, task_id)
    setter(result)
  } catch (e) {
    error.value = e.message
    activeTab.value = null
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <div class="card-ring overflow-hidden mt-4">
    <!-- Tab bar -->
    <div class="flex border-b border-slate-100">
      <button
        v-for="tab in [
          { key: 'summary',   icon: '📝', label: 'AI 总结' },
          { key: 'subtitles', icon: '💬', label: '字幕' },
          { key: 'mindmap',   icon: '🧠', label: '思维导图' },
          { key: 'ask',       icon: '💡', label: '问答' },
        ]"
        :key="tab.key"
        @click="tab.key === 'summary' ? loadSummary() : tab.key === 'subtitles' ? loadSubtitles() : tab.key === 'mindmap' ? loadMindmap() : (activeTab = 'ask')"
        class="flex-1 px-3 py-3.5 text-sm font-medium transition-all duration-200 border-b-2 -mb-px"
        :class="activeTab === tab.key
          ? 'text-[#3a5df9] border-[#3a5df9] bg-blue-50/30'
          : 'text-slate-400 border-transparent hover:text-slate-600 hover:bg-slate-50'"
      >
        <span class="mr-1.5">{{ tab.icon }}</span>{{ tab.label }}
      </button>
    </div>

    <!-- Content area -->
    <div class="p-5 min-h-[160px]">
      <!-- Loading -->
      <div v-if="isLoading" class="flex items-center justify-center py-10 gap-3">
        <div class="w-6 h-6 border-3 border-[#3a5df9]/20 border-t-[#3a5df9] rounded-full animate-spin"></div>
        <span class="text-sm text-slate-400">AI 处理中...</span>
      </div>

      <!-- Error -->
      <div v-else-if="error" class="p-4 rounded-lg bg-amber-50 border border-amber-200 text-sm text-amber-700">
        {{ error }}
      </div>

      <!-- Empty -->
      <div v-else-if="!activeTab" class="text-center py-10 text-slate-400 text-sm">
        选择一个功能查看 AI 分析结果
      </div>

      <!-- ── AI Summary ──────────────────────────────────────── -->
      <div v-else-if="activeTab === 'summary' && summaryResult" class="space-y-4">
        <div class="p-4 rounded-xl bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-100">
          <p class="text-xs text-blue-400 font-medium mb-1">一句话总结</p>
          <p class="text-base font-semibold text-slate-800">{{ summaryResult.one_liner }}</p>
        </div>

        <div v-if="summaryResult.chapters?.length">
          <p class="text-xs text-slate-400 font-medium mb-2">章节导航</p>
          <div class="space-y-1.5">
            <div
              v-for="(ch, i) in summaryResult.chapters"
              :key="i"
              class="flex items-start gap-3 px-3 py-2 rounded-lg hover:bg-slate-50 transition-colors"
            >
              <span class="text-xs font-mono text-[#3a5df9] bg-blue-50 px-1.5 py-0.5 rounded shrink-0 mt-0.5">
                {{ ch.timestamp }}
              </span>
              <span class="text-sm text-slate-700">{{ ch.title }}</span>
            </div>
          </div>
        </div>

        <div v-if="summaryResult.key_points?.length">
          <p class="text-xs text-slate-400 font-medium mb-2">关键要点</p>
          <ul class="space-y-1.5">
            <li v-for="(kp, i) in summaryResult.key_points" :key="i" class="flex items-start gap-2 text-sm text-slate-600">
              <span class="text-[#3a5df9] font-bold shrink-0">•</span>
              {{ kp }}
            </li>
          </ul>
        </div>

        <div v-if="summaryResult.tags?.length" class="flex flex-wrap gap-2">
          <span
            v-for="tag in summaryResult.tags"
            :key="tag"
            class="px-2.5 py-1 text-xs rounded-full bg-slate-100 text-slate-500"
          >#{{ tag }}</span>
        </div>
      </div>

      <!-- ── Subtitles ────────────────────────────────────────── -->
      <div v-else-if="activeTab === 'subtitles' && subtitleResult" class="space-y-4">
        <!-- Header -->
        <div class="flex items-center gap-2 text-sm text-slate-500">
          <span>可用语言：</span>
          <span class="font-semibold text-slate-700">{{ subtitleResult.available_langs?.length || 0 }} 种</span>
          <span v-if="subtitleResult.extracted?.length" class="text-slate-400">
            | 已提取：{{ subtitleResult.extracted.map(e => e.lang).join(', ') }}
          </span>
        </div>

        <div v-for="entry in subtitleResult.extracted" :key="entry.lang" class="space-y-3">
          <!-- Language badge -->
          <div class="flex items-center gap-2 flex-wrap">
            <span class="text-xs px-2 py-0.5 rounded font-medium"
              :class="entry.source === 'manual' ? 'bg-green-100 text-green-700' : entry.source === 'auto-translated' ? 'bg-purple-100 text-purple-700' : 'bg-amber-100 text-amber-700'">
              {{ entry.source === 'manual' ? '人工字幕' : entry.source === 'auto-translated' ? '中文翻译' : '自动字幕' }}
            </span>
            <span class="text-xs text-slate-400">[{{ entry.lang }}]</span>
            <span class="text-xs text-slate-500 font-medium">
              共 <span class="text-[#3a5df9] font-bold">{{ entry.segment_count || entry.segments?.length || 0 }}</span> 条字幕
            </span>
          </div>

          <!-- Segments list -->
          <div
            v-if="entry.segments?.length"
            class="bg-slate-50 rounded-xl border border-slate-100 overflow-hidden"
          >
            <!-- Scroll area -->
            <div class="max-h-[420px] overflow-y-auto scroll-smooth" ref="subtitleScroll">
              <!-- Show segments: first 15 or all -->
              <div
                v-for="seg in (showAll[entry.lang] ? entry.segments : entry.segments.slice(0, 15))"
                :key="seg.index"
                class="flex items-start gap-3 px-4 py-2.5 hover:bg-white/60 transition-colors border-b border-slate-100 last:border-0"
              >
                <!-- Timestamp badge -->
                <span class="text-[11px] font-mono text-[#3a5df9] bg-blue-50 px-1.5 py-0.5 rounded shrink-0 w-[68px] text-center">
                  {{ seg.start }}
                </span>
                <!-- Text -->
                <span class="text-sm text-slate-700 leading-relaxed">{{ seg.text }}</span>
              </div>

              <!-- Expand button -->
              <button
                v-if="entry.segments.length > 15 && !showAll[entry.lang]"
                @click="showAll[entry.lang] = true"
                class="w-full py-2.5 text-xs text-[#3a5df9] hover:bg-blue-50/50 transition-colors font-medium"
              >
                展开全部 {{ entry.segments.length }} 条 ▼
              </button>
              <button
                v-else-if="entry.segments.length > 15 && showAll[entry.lang]"
                @click="showAll[entry.lang] = false"
                class="w-full py-2.5 text-xs text-slate-400 hover:bg-slate-100 transition-colors"
              >
                收起 ▲
              </button>
            </div>
          </div>

          <!-- Fallback: raw text -->
          <pre
            v-else
            class="text-sm text-slate-600 whitespace-pre-wrap font-sans leading-relaxed bg-slate-50 rounded-xl p-4 max-h-[400px] overflow-y-auto"
          >{{ entry.text_preview || entry.text || '暂无内容' }}</pre>
        </div>
      </div>

      <!-- ── Mindmap ──────────────────────────────────────────── -->
      <div v-else-if="activeTab === 'mindmap' && mindmapResult" class="space-y-3">
        <pre class="text-sm text-slate-700 whitespace-pre font-mono leading-relaxed bg-gradient-to-br from-indigo-50 to-purple-50 rounded-xl p-5 max-h-[500px] overflow-y-auto border border-indigo-100">{{ mindmapResult.mindmap_text }}</pre>
      </div>

      <!-- ── AI Ask ────────────────────────────────────────────── -->
      <div v-else-if="activeTab === 'ask'" class="space-y-4">
        <!-- Chat history -->
        <div v-for="(turn, i) in askHistory" :key="i" class="space-y-2">
          <div class="flex justify-end">
            <div class="max-w-[80%] px-4 py-2.5 rounded-2xl rounded-br-md bg-[#3a5df9] text-white text-sm">
              {{ turn.question }}
            </div>
          </div>
          <div class="flex justify-start">
            <div class="max-w-[85%] px-4 py-2.5 rounded-2xl rounded-bl-md bg-slate-100 text-slate-700 text-sm whitespace-pre-wrap">
              {{ turn.answer }}
            </div>
          </div>
        </div>

        <!-- Input -->
        <div class="flex gap-2">
          <input
            v-model="askQuestion"
            @keyup.enter="submitAsk"
            :disabled="isLoading"
            placeholder="针对视频内容提问..."
            class="flex-1 px-4 py-2.5 rounded-full bg-slate-50 border border-slate-200 text-sm outline-none focus:border-[#3a5df9] focus:ring-2 focus:ring-[#3a5df9]/10 transition-all disabled:opacity-50"
          />
          <button
            @click="submitAsk"
            :disabled="isLoading || !askQuestion.trim()"
            class="px-5 py-2.5 rounded-full bg-[#3a5df9] text-white text-sm font-medium hover:opacity-90 disabled:opacity-40 transition-all"
          >
            发送
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
