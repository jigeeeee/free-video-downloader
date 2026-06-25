<script setup>
import { ref, onMounted } from "vue"

const files = ref([])
const loading = ref(false)

async function loadFiles() {
  loading.value = true
  try {
    const res = await fetch("/api/files")
    const data = await res.json()
    files.value = data.files || []
  } catch (e) {
    console.error("Failed to load files:", e)
  } finally {
    loading.value = false
  }
}

async function deleteFile(name) {
  try {
    await fetch(`/api/files/${encodeURIComponent(name)}`, { method: "DELETE" })
    files.value = files.value.filter((f) => f.name !== name)
  } catch (e) {
    console.error("Delete failed:", e)
  }
}

function openFile(name) {
  window.open(`/api/download/${encodeURIComponent(name)}`, "_blank")
}

onMounted(loadFiles)
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-5">
      <h2 class="text-lg font-bold text-slate-900">已下载视频</h2>
      <button @click="loadFiles" class="text-sm text-[#3a5df9] hover:underline">
        刷新
      </button>
    </div>

    <!-- Empty -->
    <div
      v-if="!loading && files.length === 0"
      class="text-center py-16 text-slate-400"
    >
      <p class="text-4xl mb-3">📂</p>
      <p>暂无下载视频</p>
      <p class="text-xs mt-1">粘贴链接开始下载你的第一个视频</p>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex justify-center py-8">
      <div class="w-6 h-6 border-3 border-[#3a5df9]/20 border-t-[#3a5df9] rounded-full animate-spin"></div>
    </div>

    <!-- Masonry Grid -->
    <div
      v-if="files.length > 0"
      class="masonry-grid columns-2 sm:columns-2 md:columns-3 lg:columns-4"
    >
      <div
        v-for="f in files"
        :key="f.name"
        class="card-ring overflow-hidden group cursor-pointer"
        @click="openFile(f.name)"
      >
        <!-- Thumbnail area -->
        <div class="aspect-video bg-slate-100 flex items-center justify-center text-3xl relative overflow-hidden">
          <span class="transition-transform duration-500 group-hover:scale-110">🎬</span>
          <div
            class="absolute inset-0 bg-gradient-to-t from-black/20 to-transparent opacity-0 transition-opacity duration-500 group-hover:opacity-100"
          ></div>
        </div>
        <!-- Info -->
        <div class="p-3">
          <h3
            class="text-sm font-bold text-slate-900 line-clamp-2 group-hover:text-[#3a5df9] transition-colors leading-snug"
            :title="f.name"
          >
            {{ f.name }}
          </h3>
          <div class="flex items-center justify-between mt-2">
            <span class="text-xs text-slate-500">{{ f.size_str }}</span>
            <button
              @click.stop="deleteFile(f.name)"
              class="text-xs text-slate-400 hover:text-red-500 transition-colors"
              title="删除"
            >
              🗑
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
