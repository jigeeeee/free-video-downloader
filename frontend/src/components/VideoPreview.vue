<script setup>
import { computed } from "vue"

const props = defineProps({
  info: Object,
})

const platformColors = {
  YouTube: "bg-red-500",
  Bilibili: "bg-pink-500",
  "Twitter/X": "bg-sky-500",
  TikTok: "bg-black",
  Instagram: "bg-gradient-to-r from-purple-500 to-pink-500",
}

const platformColor = computed(() => platformColors[props.info.platform] || "bg-slate-500")
</script>

<template>
  <div class="card-ring overflow-hidden">
    <div class="flex flex-col sm:flex-row">
      <!-- Thumbnail -->
      <div class="sm:w-64 shrink-0 aspect-video sm:aspect-auto relative bg-slate-100 overflow-hidden">
        <img
          v-if="info.thumbnail"
          :src="info.thumbnail"
          :alt="info.title"
          class="w-full h-full object-cover transition-all duration-700 hover:scale-105"
        />
        <div v-else class="w-full h-full flex items-center justify-center text-slate-300 text-4xl">
          🎬
        </div>
        <!-- Platform badge -->
        <span
          class="absolute top-3 left-3 rounded-full px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-white"
          :class="platformColor"
        >
          {{ info.platform || "Video" }}
        </span>
      </div>

      <!-- Info -->
      <div class="flex-1 p-5 flex flex-col justify-between">
        <div>
          <h2 class="text-lg font-bold text-slate-900 leading-snug line-clamp-2">
            {{ info.title }}
          </h2>
          <div class="flex flex-wrap items-center gap-3 mt-2 text-sm text-slate-500">
            <span v-if="info.uploader" class="flex items-center gap-1">
              <span>👤</span> {{ info.uploader }}
            </span>
            <span v-if="info.duration_str" class="flex items-center gap-1">
              <span>⏱</span> {{ info.duration_str }}
            </span>
          </div>
        </div>
        <p class="text-xs text-slate-400 mt-3 truncate">
          {{ info.webpage_url }}
        </p>
      </div>
    </div>
  </div>
</template>
