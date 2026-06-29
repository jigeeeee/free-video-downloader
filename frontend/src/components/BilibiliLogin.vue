<script setup>
import { ref, onUnmounted } from "vue"

const emit = defineEmits(["close"])
const show = ref(false)
const qrUrl = ref("")
const qrKey = ref("")
const status = ref("waiting")
const pollTimer = ref(null)

const statusText = {
  waiting: "等待扫码...",
  scanned: "已扫描，请在手机上确认",
  confirmed: "登录成功！Cookie 已保存",
  expired: "二维码已过期",
}

async function open() {
  show.value = true
  status.value = "waiting"
  try {
    const res = await fetch("/api/bilibili/qrcode")
    const data = await res.json()
    qrUrl.value = `https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=${encodeURIComponent(data.url)}`
    qrKey.value = data.qrcode_key
    startPolling()
  } catch (e) {
    status.value = "error"
  }
}

function startPolling() {
  if (pollTimer.value) clearInterval(pollTimer.value)
  pollTimer.value = setInterval(async () => {
    try {
      const res = await fetch(`/api/bilibili/qrcode/status?qrcode_key=${qrKey.value}`)
      const data = await res.json()
      status.value = data.status
      if (data.status === "confirmed") {
        clearInterval(pollTimer.value)
        setTimeout(() => { show.value = false; emit("close") }, 1500)
      }
      if (data.status === "expired") {
        clearInterval(pollTimer.value)
      }
    } catch (e) {}
  }, 2000)
}

function close() {
  show.value = false
  if (pollTimer.value) clearInterval(pollTimer.value)
}

onUnmounted(() => {
  if (pollTimer.value) clearInterval(pollTimer.value)
})

defineExpose({ open })
</script>

<template>
  <Teleport to="body">
    <div
      v-if="show"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
      @click.self="close"
    >
      <div class="bg-white rounded-2xl shadow-2xl p-8 max-w-sm w-full mx-4 text-center">
        <h2 class="text-xl font-bold text-slate-800 mb-4">📱 Bilibili 扫码登录</h2>

        <img
          v-if="qrUrl"
          :src="qrUrl"
          alt="QR Code"
          class="mx-auto rounded-xl border border-slate-200 w-[250px] h-[250px]"
        />

        <p class="mt-4 text-sm font-medium"
          :class="{
            'text-slate-400': status === 'waiting',
            'text-blue-500': status === 'scanned',
            'text-green-500': status === 'confirmed',
            'text-red-400': status === 'expired',
          }"
        >{{ statusText[status] || '等待中...' }}</p>

        <div class="mt-4 text-xs text-slate-400 text-left leading-relaxed">
          <p>1. 打开哔哩哔哩 App</p>
          <p>2. 点击右上角「扫一扫」</p>
          <p>3. 扫描二维码并确认登录</p>
        </div>

        <button
          @click="close"
          class="mt-6 px-6 py-2 text-sm rounded-full bg-slate-100 text-slate-500 hover:bg-slate-200 transition-colors"
        >
          {{ status === 'confirmed' ? '完成' : '取消' }}
        </button>
      </div>
    </div>
  </Teleport>
</template>
