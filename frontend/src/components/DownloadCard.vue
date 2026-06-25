<script setup>
import { computed } from "vue"

const props = defineProps({
  task: Object,
})

const percent = computed(() => Math.round(props.task.percent || 0))
const isDone = computed(() => props.task.status === "done")
const isError = computed(() => props.task.status === "error")
</script>

<template>
  <div
    class="card-ring p-5 space-y-3"
    :class="{
      'ring-green-200 bg-green-50/50': isDone,
      'ring-red-200 bg-red-50/50': isError,
    }"
  >
    <!-- Header -->
    <div class="flex items-center justify-between">
      <span class="text-sm font-semibold text-slate-700">
        <span v-if="isDone">✅ 下载完成</span>
        <span v-else-if="isError">❌ 下载失败</span>
        <span v-else>⬇️ 正在下载...</span>
      </span>
      <span class="text-xs text-slate-400">{{ task.task_id }}</span>
    </div>

    <!-- Progress Bar -->
    <div class="relative h-3 bg-slate-100 rounded-full overflow-hidden">
      <div
        class="absolute inset-y-0 left-0 rounded-full transition-all duration-500"
        :class="{
          'bg-[#3a5df9]': !isDone && !isError,
          'bg-green-500': isDone,
          'bg-red-400': isError,
        }"
        :style="{ width: percent + '%' }"
      ></div>
    </div>

    <!-- Stats -->
    <div class="flex flex-wrap items-center gap-4 text-xs text-slate-500">
      <span class="font-bold text-slate-700">{{ percent }}%</span>
      <span v-if="task.speed">🚀 {{ task.speed }}</span>
      <span v-if="task.eta">⏳ 剩余 {{ task.eta }}</span>
      <span v-if="task.filesize_str">📦 {{ task.filesize_str }}</span>
      <span v-if="task.filename" class="text-[#3a5df9] font-mono truncate max-w-[300px]">
        📁 {{ task.filename }}
      </span>
    </div>

    <!-- Error -->
    <div
      v-if="isError && task.error"
      class="p-3 rounded-lg bg-red-100 text-red-700 text-xs font-mono break-all"
    >
      {{ task.error }}
    </div>
  </div>
</template>
