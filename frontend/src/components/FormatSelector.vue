<script setup>
defineProps({
  formats: Array,
  selected: Object,
})

const emit = defineEmits(["select"])
</script>

<template>
  <div class="space-y-3">
    <h3 class="text-sm font-semibold text-slate-700">
      选择清晰度 / 格式
      <span class="text-xs font-normal text-slate-400 ml-2">
        (视频+音频自动合并)
      </span>
    </h3>
    <div class="flex flex-wrap gap-2">
      <button
        v-for="f in formats"
        :key="f.format_id"
        @click="emit('select', f)"
        class="relative group rounded-full px-4 py-2.5 text-sm font-medium transition-all duration-300"
        :class="
          selected?.format_id === f.format_id
            ? 'bg-[#3a5df9] text-white shadow-lg shadow-blue-500/25'
            : 'bg-white text-slate-600 ring-1 ring-slate-200 hover:ring-[#3a5df9]/40 hover:text-[#3a5df9] hover:bg-blue-50/50'
        "
      >
        <span class="font-bold">{{ f.resolution }}</span>
        <span class="ml-1.5 opacity-70 text-xs">.{{ f.ext }}</span>
        <span v-if="f.filesize_str" class="ml-1.5 opacity-50 text-xs">({{ f.filesize_str }})</span>
        <span
          v-if="f.video_only"
          class="ml-1 text-[10px] opacity-50"
          :class="selected?.format_id === f.format_id ? '' : 'text-amber-500'"
        >+音频</span>
      </button>
    </div>
    <p v-if="formats.length === 0" class="text-sm text-slate-400">
      未找到可用格式
    </p>
  </div>
</template>
