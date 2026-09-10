<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import { Download, X } from "@lucide/vue";

interface InstallPrompt extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}
const prompt = ref<InstallPrompt | null>(null);
const showHelp = ref(false);
const installed = ref(false);
const secure = window.isSecureContext;
const standalone = window.matchMedia("(display-mode: standalone)");
function updateInstalled() {
  installed.value =
    standalone.matches ||
    !!(navigator as Navigator & { standalone?: boolean }).standalone;
}
function beforeInstall(event: Event) {
  event.preventDefault();
  prompt.value = event as InstallPrompt;
}
function didInstall() {
  installed.value = true;
  prompt.value = null;
  showHelp.value = false;
}
async function install() {
  const event = prompt.value;
  if (!event) {
    showHelp.value = !showHelp.value;
    return;
  }
  try {
    await event.prompt();
    await event.userChoice;
  } finally {
    prompt.value = null;
  }
}
onMounted(() => {
  updateInstalled();
  window.addEventListener("beforeinstallprompt", beforeInstall);
  window.addEventListener("appinstalled", didInstall);
  standalone.addEventListener("change", updateInstalled);
});
onUnmounted(() => {
  window.removeEventListener("beforeinstallprompt", beforeInstall);
  window.removeEventListener("appinstalled", didInstall);
  standalone.removeEventListener("change", updateInstalled);
});
</script>

<template>
  <div v-if="!installed" class="install-app">
    <button class="text-button" :aria-expanded="showHelp" @click="install">
      <Download :size="16" /> Add to home screen
    </button>
    <div
      v-if="showHelp"
      class="install-help"
      role="region"
      aria-label="Add to home screen instructions"
    >
      <button
        class="icon-button"
        aria-label="Close install instructions"
        @click="showHelp = false"
      >
        <X :size="17" />
      </button>
      <strong>Keep Simple Transcription close.</strong>
      <p v-if="!secure">
        Open the app’s HTTPS address first. On a phone, an HTTP LAN or Tailscale
        IP cannot save the offline connection page.
      </p>
      <p v-else>
        On iPhone or iPad, open this page in Safari, tap Share, then Add to Home
        Screen. On Android, use your browser’s Install app or Add to Home screen
        option.
      </p>
      <p>
        Visit once while connected so the “check Tailscale” page can be saved.
        Your browser must allow offline storage.
      </p>
    </div>
  </div>
</template>
