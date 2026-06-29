<script setup>
import { onMounted, onUnmounted, ref } from "vue"

const tasks = ref([])
const history = ref({ files: [], ai_results: [] })
const loading = ref(false)
const timer = ref(null)

async function loadAll() {
  loading.value = true
  try {
    const [tasksRes, historyRes] = await Promise.all([
      fetch("/api/tasks"),
      fetch("/api/history"),
    ])
    if (tasksRes.ok) tasks.value = (await tasksRes.json()).tasks || []
    if (historyRes.ok) history.value = await historyRes.json()
  } catch (e) {
    console.warn("Task center refresh failed", e)
  } finally {
    loading.value = false
  }
}

async function retryTask(task) {
  try {
    const res = await fetch(`/api/tasks/${task.task_id}/retry`, { method: "POST" })
    if (res.ok) loadAll()
  } catch (e) {
    console.warn("Retry failed", e)
  }
}

function taskLabel(type) {
  return {
    download: "下载",
    subtitle: "字幕",
    summary: "总结",
    mindmap: "导图",
    ask: "问答",
    transcribe: "转录",
    convert: "转换",
    rewrite: "改写",
  }[type] || type
}

onMounted(() => {
  loadAll()
  timer.value = setInterval(loadAll, 3000)
})

onUnmounted(() => {
  if (timer.value) clearInterval(timer.value)
})
</script>

<template>
  <section class="mt-16">
    <div class="flex items-center justify-between mb-5">
      <h2 class="text-lg font-bold text-slate-900">任务中心</h2>
      <button @click="loadAll" class="text-sm text-[#3a5df9] hover:underline">
        {{ loading ? "刷新中..." : "刷新" }}
      </button>
    </div>

    <div class="grid gap-3 md:grid-cols-2">
      <div
        v-for="task in tasks.slice(0, 8)"
        :key="task.task_id"
        class="card-ring p-4"
      >
        <div class="flex items-center justify-between gap-3">
          <div class="min-w-0">
            <p class="text-sm font-semibold text-slate-800">
              {{ taskLabel(task.task_type) }}
              <span class="text-xs font-normal text-slate-400 ml-1">{{ task.task_id }}</span>
            </p>
            <p class="text-xs text-slate-400 truncate mt-1">
              {{ task.metadata?.url || task.metadata?.filename || task.result?.filename || task.created_at }}
            </p>
          </div>
          <span
            class="text-xs px-2 py-1 rounded-full shrink-0"
            :class="{
              'bg-green-100 text-green-700': task.status === 'done',
              'bg-blue-100 text-blue-700': task.status === 'processing' || task.status === 'queued',
              'bg-red-100 text-red-700': task.status === 'error',
            }"
          >
            {{ task.status }}
          </span>
        </div>
        <div class="h-2 bg-slate-100 rounded-full overflow-hidden mt-3">
          <div class="h-full bg-[#3a5df9] transition-all" :style="{ width: Math.round(task.percent || 0) + '%' }"></div>
        </div>
        <div class="flex items-center justify-between mt-2">
          <span class="text-xs text-slate-400">{{ Math.round(task.percent || 0) }}%</span>
          <button
            v-if="task.status === 'error'"
            @click="retryTask(task)"
            class="text-xs text-[#3a5df9] hover:underline"
          >
            重试
          </button>
        </div>
      </div>

      <div v-if="tasks.length === 0" class="text-sm text-slate-400 py-8">
        暂无任务记录
      </div>
    </div>

    <div v-if="history.ai_results?.length" class="mt-6">
      <p class="text-sm font-semibold text-slate-700 mb-3">最近 AI 结果</p>
      <div class="flex flex-wrap gap-2">
        <span
          v-for="item in history.ai_results.slice(0, 10)"
          :key="item.id"
          class="text-xs px-2.5 py-1 rounded-full bg-slate-100 text-slate-500"
        >
          {{ taskLabel(item.result_type) }} · {{ item.title || item.task_id }}
        </span>
      </div>
    </div>
  </section>
</template>
