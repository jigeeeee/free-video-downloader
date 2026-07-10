<script setup>
import { computed, onMounted, ref } from "vue"

const status = ref(null)

const platforms = computed(() => {
  const data = status.value?.platforms || {}
  return [
    ["youtube", "YouTube"],
    ["bilibili", "Bilibili"],
    ["douyin", "Douyin"],
  ].map(([key, label]) => {
    const item = data[key] || {}
    return {
      key,
      label,
      ready: Boolean(item.has_cookie_source),
      source: item.cookiefile ? "synced" : item.browser ? "browser" : item.fallback_cookiefile ? "generic" : "missing",
    }
  })
})

async function loadStatus() {
  try {
    const res = await fetch("/api/cookies/status")
    if (res.ok) status.value = await res.json()
  } catch (e) {}
}

onMounted(loadStatus)
</script>

<template>
  <div v-if="status" class="mb-8 flex flex-wrap items-center justify-center gap-2 text-xs">
    <span
      v-for="item in platforms"
      :key="item.key"
      class="inline-flex items-center gap-1 rounded-full border px-3 py-1.5 font-medium"
      :class="item.ready ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-slate-200 bg-white text-slate-500'"
      :title="`${item.label}: ${item.source}`"
    >
      <span class="h-2 w-2 rounded-full" :class="item.ready ? 'bg-emerald-500' : 'bg-slate-300'"></span>
      <span>{{ item.label }}</span>
      <span class="text-slate-400">{{ item.source }}</span>
    </span>
  </div>
</template>
