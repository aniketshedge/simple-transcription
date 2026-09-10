import { createApp } from "vue";
import App from "./App.vue";
import "./style.css";

createApp(App).mount("#app");

// HTTPS is required on phones; localhost is also allowed for development/testing.
if (
  import.meta.env.PROD &&
  window.isSecureContext &&
  "serviceWorker" in navigator
) {
  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register("/sw.js", { updateViaCache: "none" })
      .catch(() => {
        // Normal online use remains available if storage or service workers are disabled.
        console.warn(
          "The offline connection page could not be saved on this device.",
        );
      });
  });
}
