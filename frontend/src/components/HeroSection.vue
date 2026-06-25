<script setup>
const features = [
  { icon: "⚡", text: "极速下载", desc: "多线程加速" },
  { icon: "🎬", text: "高清无损", desc: "支持 4K/8K" },
  { icon: "🌍", text: "100+ 平台", desc: "全覆盖" },
  { icon: "📱", text: "手机可用", desc: "响应式设计" },
]
</script>

<template>
  <section class="hero-bg pt-16 pb-24">
    <div class="max-w-4xl mx-auto px-4 text-center">
      <!-- Badge -->
      <div class="inline-flex items-center gap-2 rounded-full bg-white/80 backdrop-blur-sm ring-1 ring-slate-200/60 px-4 py-1.5 mb-6">
        <span class="w-2 h-2 rounded-full bg-green-400 animate-pulse"></span>
        <span class="text-xs font-medium text-slate-500">开源免费 · 持续更新</span>
      </div>

      <!-- Title -->
      <h1 class="text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tight text-slate-900 leading-tight">
        万能
        <span class="bg-gradient-to-r from-[#3a5df9] to-[#6d8aff] bg-clip-text text-transparent">
          视频下载器
        </span>
      </h1>

      <!-- Subtitle -->
      <p class="mt-5 text-lg sm:text-xl text-slate-500 max-w-2xl mx-auto leading-relaxed">
        粘贴链接，选择清晰度，一键下载。
        <span class="text-slate-400">支持 YouTube、Bilibili、Twitter 等 100+ 平台。</span>
      </p>

      <!-- Feature badges -->
      <div class="flex flex-wrap items-center justify-center gap-2.5 mt-8">
        <div
          v-for="f in features"
          :key="f.text"
          class="glass-badge flex items-center gap-1.5 !text-[11px] !px-3 !py-1.5"
        >
          <span>{{ f.icon }}</span>
          <span>{{ f.text }}</span>
          <span class="opacity-50">·</span>
          <span class="opacity-60">{{ f.desc }}</span>
        </div>
      </div>
    </div>
  </section>
</template>
