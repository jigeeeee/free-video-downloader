<script setup>
import { ref } from "vue"

const props = defineProps({
  loading: Boolean,
})

const emit = defineEmits(["submit"])
const url = ref("")

function handleSubmit() {
  const val = url.value.trim()
  if (val) emit("submit", val)
}
</script>

<template>
  <div class="flex justify-center">
    <form @submit.prevent="handleSubmit" class="search-bar">
      <span class="text-[#3a5df9] text-xl shrink-0">🔗</span>
      <input
        v-model="url"
        type="url"
        placeholder="粘贴视频链接，如 https://www.youtube.com/watch?v=..."
        class="flex-1 outline-none border-none text-sm placeholder:text-slate-400 bg-transparent"
        :disabled="loading"
      />
      <button
        type="submit"
        :disabled="loading || !url.trim()"
        class="btn-primary text-sm px-5 py-1.5 shrink-0 disabled:opacity-40 disabled:cursor-not-allowed"
      >
        <span v-if="loading" class="inline-flex items-center gap-1">
          <span class="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
          解析中
        </span>
        <span v-else>解析</span>
      </button>
    </form>
  </div>
</template>
