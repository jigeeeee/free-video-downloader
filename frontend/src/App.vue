<script setup>
import { ref, computed } from "vue"
import HeroSection from "./components/HeroSection.vue"
import URLInput from "./components/URLInput.vue"
import VideoPreview from "./components/VideoPreview.vue"
import FormatSelector from "./components/FormatSelector.vue"
import DownloadCard from "./components/DownloadCard.vue"
import VideoLibrary from "./components/VideoLibrary.vue"

const videoInfo = ref(null)
const isLoading = ref(false)
const error = ref(null)
const selectedFormat = ref(null)
const downloadTask = ref(null)
const progressTimer = ref(null)

async function fetchInfo(url) {
  isLoading.value = true
  error.value = null
  videoInfo.value = null
  selectedFormat.value = null
  downloadTask.value = null
  try {
    const res = await fetch("/api/info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    })
    if (!res.ok) {
      const err = await res.json()
      throw new Error(err.detail || "Failed to fetch video info")
    }
    videoInfo.value = await res.json()
    if (videoInfo.value.formats.length > 0) {
      selectedFormat.value = videoInfo.value.formats[0]
    }
  } catch (e) {
    error.value = e.message
  } finally {
    isLoading.value = false
  }
}

async function startDownload() {
  if (!videoInfo.value || !selectedFormat.value) return
  error.value = null
  try {
    const res = await fetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: videoInfo.value.webpage_url,
        format_id: selectedFormat.value.format_id,
      }),
    })
    if (!res.ok) {
      const err = await res.json()
      throw new Error(err.detail || "Download failed")
    }
    downloadTask.value = await res.json()
    pollProgress()
  } catch (e) {
    error.value = e.message
  }
}

function pollProgress() {
  if (!downloadTask.value) return
  const tid = downloadTask.value.task_id
  const poll = async () => {
    try {
      const res = await fetch(`/api/progress/${tid}`)
      if (!res.ok) return
      const data = await res.json()
      downloadTask.value = data
      if (data.status === "done" || data.status === "error") {
        if (progressTimer.value) {
          clearInterval(progressTimer.value)
          progressTimer.value = null
        }
      }
    } catch (e) {}
  }
  poll()
  progressTimer.value = setInterval(poll, 1000)
}

function resetAll() {
  videoInfo.value = null
  isLoading.value = false
  error.value = null
  selectedFormat.value = null
  downloadTask.value = null
  if (progressTimer.value) {
    clearInterval(progressTimer.value)
    progressTimer.value = null
  }
}

const statusText = computed(() => {
  if (!downloadTask.value) return ""
  const t = downloadTask.value
  if (t.status === "queued") return "queued..."
  if (t.status === "downloading") return "downloading " + Math.round(t.percent) + "%"
  if (t.status === "done") return "Done!"
  if (t.status === "error") return "Failed"
  return ""
})
</script>

<template>
  <div class="min-h-screen">
    <HeroSection />

    <main class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 pb-24">
      <div class="relative -mt-16 mb-8">
        <URLInput @submit="fetchInfo" :loading="isLoading" />
      </div>

      <!-- Error display with pre-formatted cookie help -->
      <div v-if="error" class="mb-8 p-5 rounded-xl bg-amber-50 border border-amber-200">
        <div class="flex items-start gap-3">
          <span class="text-lg shrink-0">&#9888;</span>
          <div class="flex-1 min-w-0">
            <p class="font-semibold text-amber-800 mb-2">Parse Failed</p>
            <pre class="text-sm text-amber-700 whitespace-pre-wrap font-sans leading-relaxed">{{ error }}</pre>
          </div>
          <button @click="error = null" class="text-amber-400 hover:text-amber-600 shrink-0">&times;</button>
        </div>
      </div>

      <div v-if="isLoading" class="flex flex-col items-center py-16 gap-4">
        <div class="w-10 h-10 border-4 border-[#3a5df9]/20 border-t-[#3a5df9] rounded-full animate-spin"></div>
        <p class="text-slate-400 text-sm">Parsing video info...</p>
      </div>

      <div v-if="videoInfo && !isLoading" class="space-y-6">
        <VideoPreview :info="videoInfo" />
        <FormatSelector :formats="videoInfo.formats" :selected="selectedFormat" @select="selectedFormat = $event" />

        <div class="flex justify-center">
          <button
            v-if="!downloadTask || downloadTask.status === 'error'"
            @click="startDownload"
            :disabled="!selectedFormat"
            class="btn-primary px-10 py-3.5 text-base font-semibold inline-flex items-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <span>Download</span>
            <span v-if="selectedFormat" class="text-white/70 text-sm font-normal">
              {{ selectedFormat.resolution }} / {{ selectedFormat.ext }}
            </span>
          </button>
        </div>

        <DownloadCard v-if="downloadTask" :task="downloadTask" />

        <p
          v-if="statusText && downloadTask?.status !== 'downloading'"
          class="text-center text-sm font-medium"
          :class="downloadTask?.status === 'done' ? 'text-green-600' : 'text-red-600'"
        >{{ statusText }}</p>

        <div v-if="downloadTask?.status === 'done' || downloadTask?.status === 'error'" class="text-center">
          <button @click="resetAll" class="btn-secondary px-6 py-2 text-sm">Reset</button>
        </div>
      </div>

      <div class="mt-16">
        <VideoLibrary />
      </div>
    </main>

    <footer class="border-t border-slate-100 py-8 text-center text-xs text-slate-400">
      <p>Universal Video Downloader / Powered by yt-dlp</p>
      <p class="mt-1">For learning purposes only. Respect copyright.</p>
    </footer>
  </div>
</template>
