<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import {
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  AudioLines,
  Check,
  CheckCircle2,
  ChevronDown,
  Clock3,
  FileAudio,
  FileText,
  FolderOpen,
  LoaderCircle,
  Plus,
  Search,
  ShieldCheck,
  Trash2,
  Upload,
  X,
  CircleAlert,
  Monitor,
  Users,
  WifiOff,
} from "@lucide/vue";
import type { Config, Job, TranscriptFile } from "./types";
import InstallApp from "./components/InstallApp.vue";
import { wiki } from "./wiki";

const jobs = ref<Job[]>([]);
const total = ref(0);
const page = ref(0);
const config = ref<Config | null>(null);
const selected = ref<Job | null>(null);
const view = ref<"history" | "new" | "detail">("history");
const loading = ref(true);
const error = ref("");
const serverUnavailable = ref(false);
const checkingConnection = ref(false);
const query = ref("");
const filter = ref("all");
const name = ref("");
const model = ref("small");
const diarize = ref(false);
const files = ref<File[]>([]);
const input = ref<HTMLInputElement | null>(null);
const uploading = ref(false);
const uploadPercent = ref(0);
const uploadLabel = ref("");
const formError = ref("");
const working = ref(false);
const preview = ref<{
  file: TranscriptFile;
  text: string;
  truncated: boolean;
} | null>(null);
const previewDialog = ref<HTMLDialogElement | null>(null);
const confirmDialog = ref<HTMLDialogElement | null>(null);
const pendingAction = ref<"delete" | "cancel">("delete");
let polling: ReturnType<typeof setTimeout> | undefined;
let alive = true;
let xhr: XMLHttpRequest | null = null;
let uploadingJob: string | null = null;
let uploadCancelled = false;

class ServerUnavailableError extends Error {
  constructor() {
    super(
      "Can’t reach your server. Check Tailscale or your home Wi-Fi connection.",
    );
  }
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(`/api${path}`, {
      ...init,
      signal: controller.signal,
    });
    if ([502, 503, 504].includes(response.status))
      throw new ServerUnavailableError();
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(
        typeof data.detail === "string"
          ? data.detail
          : `Request failed (${response.status}).`,
      );
    }
    return response.status === 204 ? (undefined as T) : await response.json();
  } catch (error) {
    if (controller.signal.aborted || error instanceof TypeError)
      throw new ServerUnavailableError();
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}
const visibleJobs = computed(() =>
  jobs.value.filter(
    (job) =>
      job.name.toLowerCase().includes(query.value.toLowerCase()) &&
      (filter.value === "all" ||
        (filter.value === "active"
          ? active(job)
          : ["completed", "partial"].includes(job.status))),
  ),
);
const activeJobs = computed(() => jobs.value.filter(active).length);
const completedJobs = computed(
  () =>
    jobs.value.filter((j) => ["completed", "partial"].includes(j.status))
      .length,
);
const uploadBytes = computed(() =>
  files.value.reduce((sum, file) => sum + file.size, 0),
);
const downloadable = computed(() =>
  selected.value?.files.some((f) => f.has_transcript),
);
const canDelete = computed(
  () =>
    selected.value &&
    !selected.value.files.some((f) =>
      ["queued", "processing", "uploading"].includes(f.status),
    ),
);
function active(job: Job) {
  return ["queued", "processing", "uploading"].includes(job.status);
}
function bytes(value: number) {
  if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(1)} GB`;
  return `${Math.max(0.1, value / 1024 ** 2).toFixed(1)} MB`;
}
function date(value: number) {
  return new Date(value * 1000).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
function duration(value: number) {
  const minutes = Math.ceil(value / 60);
  return minutes >= 60
    ? `${Math.floor(minutes / 60)}h ${minutes % 60}m`
    : `${minutes} min`;
}
function statusLabel(job: Job) {
  if (job.cancel_requested && active(job)) return "Cancelling";
  return (
    (
      {
        processing: "In progress",
        queued: "Queued",
        uploading: "Upload incomplete",
        completed: "Complete",
        partial: "Partial result",
        failed: "Failed",
        cancelled: "Cancelled",
      } as Record<string, string>
    )[job.status] || job.status
  );
}
function jobProgress(job: Job) {
  return job.files.length
    ? Math.round((job.finished_files / job.files.length) * 100)
    : 0;
}

async function refresh() {
  if (checkingConnection.value) return;
  checkingConnection.value = true;
  try {
    const [list, serverConfig] = await Promise.all([
      api<{ jobs: Job[]; total: number }>(`/jobs?offset=${page.value * 50}`),
      config.value ? Promise.resolve(config.value) : api<Config>("/config"),
    ]);
    jobs.value = list.jobs;
    total.value = list.total;
    config.value = serverConfig;
    serverUnavailable.value = false;
    const selectedId = selected.value?.id;
    if (selectedId) {
      const detail = await api<Job>(`/jobs/${selectedId}`);
      if (selected.value?.id === selectedId) selected.value = detail;
    }
    error.value = "";
  } catch (e) {
    serverUnavailable.value = e instanceof ServerUnavailableError;
    error.value =
      e instanceof Error ? e.message : "Could not reach your server.";
  } finally {
    loading.value = false;
    checkingConnection.value = false;
  }
}
async function poll() {
  if (document.visibilityState === "visible") await refresh();
  if (alive) polling = setTimeout(poll, 3000);
}
async function changePage(direction: number) {
  page.value += direction;
  await refresh();
}
function openJob(job: Job) {
  selected.value = job;
  view.value = "detail";
  window.scrollTo(0, 0);
}
function home() {
  view.value = "history";
  selected.value = null;
  window.scrollTo(0, 0);
}
function newJob() {
  name.value = "";
  files.value = [];
  model.value = "small";
  formError.value = "";
  diarize.value = !!config.value?.speaker_labels_available;
  view.value = "new";
  selected.value = null;
  window.scrollTo(0, 0);
}
function addFiles(list: FileList | null) {
  if (!list || uploading.value || !config.value) return;
  formError.value = "";
  for (const file of Array.from(list)) {
    if (file.size === 0) {
      formError.value = `${file.name} is empty.`;
      continue;
    }
    if (file.size > config.value.max_file_bytes) {
      formError.value = `${file.name} exceeds the ${bytes(config.value.max_file_bytes)} limit.`;
      continue;
    }
    if (files.value.length >= config.value.max_files) {
      formError.value = `Choose up to ${config.value.max_files} files.`;
      break;
    }
    if (
      !files.value.some(
        (f) =>
          f.name === file.name &&
          f.size === file.size &&
          f.lastModified === file.lastModified,
      )
    )
      files.value.push(file);
  }
  if (input.value) input.value.value = "";
}
function drop(event: DragEvent) {
  addFiles(event.dataTransfer?.files ?? null);
}
function uploadFile(
  jobId: string,
  file: File,
  completed: number,
  totalBytes: number,
) {
  return new Promise<void>((resolve, reject) => {
    xhr = new XMLHttpRequest();
    xhr.open(
      "PUT",
      `/api/jobs/${jobId}/files?filename=${encodeURIComponent(file.name)}`,
    );
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.upload.onprogress = (event) => {
      uploadPercent.value = Math.min(
        100,
        Math.round(((completed + event.loaded) / totalBytes) * 100),
      );
    };
    xhr.onload = () => {
      if (xhr!.status >= 200 && xhr!.status < 300) resolve();
      else {
        let message =
          "Upload failed. Check your connection and available server storage.";
        try {
          message = JSON.parse(xhr!.responseText).detail || message;
        } catch {
          /* non-JSON proxy error */
        }
        reject(new Error(message));
      }
    };
    xhr.onerror = () =>
      reject(
        new Error("Upload interrupted. Keep this page open and try again."),
      );
    xhr.onabort = () => reject(new Error("Upload cancelled."));
    xhr.send(file);
  });
}
async function createJob() {
  if (uploading.value || !files.value.length || !name.value.trim()) return;
  uploading.value = true;
  uploadCancelled = false;
  formError.value = "";
  uploadPercent.value = 0;
  try {
    const job = await api<Job>("/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: name.value.trim(),
        model: model.value,
        diarize: diarize.value,
      }),
    });
    uploadingJob = job.id;
    let completed = 0;
    for (const [index, file] of files.value.entries()) {
      if (uploadCancelled) throw new Error("Upload cancelled.");
      uploadLabel.value = `Uploading ${index + 1} of ${files.value.length}: ${file.name}`;
      await uploadFile(job.id, file, completed, uploadBytes.value);
      completed += file.size;
    }
    if (uploadCancelled) throw new Error("Upload cancelled.");
    uploadLabel.value = "Adding to the queue…";
    const submitted = await api<Job>(`/jobs/${job.id}/submit`, {
      method: "POST",
    });
    uploadingJob = null;
    openJob(submitted);
    await refresh();
  } catch (e) {
    formError.value =
      e instanceof Error ? e.message : "Could not create the job.";
    if (uploadingJob) {
      await api(`/jobs/${uploadingJob}/cancel`, { method: "POST" }).catch(
        () => {
          formError.value +=
            " The server could not confirm cleanup. Incomplete uploads expire automatically.";
        },
      );
    }
  } finally {
    uploading.value = false;
    uploadingJob = null;
    xhr = null;
  }
}
function cancelUpload() {
  uploadCancelled = true;
  xhr?.abort();
}
function confirmAction(action: "delete" | "cancel") {
  pendingAction.value = action;
  confirmDialog.value?.showModal();
}
async function performAction() {
  if (!selected.value) return;
  working.value = true;
  try {
    if (pendingAction.value === "delete") {
      await api(`/jobs/${selected.value.id}`, { method: "DELETE" });
      home();
    } else await api(`/jobs/${selected.value.id}/cancel`, { method: "POST" });
    confirmDialog.value?.close();
    await refresh();
  } catch (e) {
    error.value = (e as Error).message;
    confirmDialog.value?.close();
  } finally {
    working.value = false;
  }
}
async function showPreview(file: TranscriptFile) {
  try {
    const text = await api<{ text: string; truncated: boolean }>(
      `/files/${file.id}/preview`,
    );
    preview.value = { file, ...text };
    previewDialog.value?.showModal();
  } catch (e) {
    error.value = (e as Error).message;
  }
}
function beforeUnload(event: BeforeUnloadEvent) {
  if (uploading.value) {
    event.preventDefault();
    event.returnValue = "";
  }
}
function checkOnReturn() {
  if (document.visibilityState === "visible") void refresh();
}
onMounted(() => {
  poll();
  window.addEventListener("beforeunload", beforeUnload);
  window.addEventListener("online", checkOnReturn);
  document.addEventListener("visibilitychange", checkOnReturn);
});
onUnmounted(() => {
  alive = false;
  clearTimeout(polling);
  window.removeEventListener("beforeunload", beforeUnload);
  window.removeEventListener("online", checkOnReturn);
  document.removeEventListener("visibilitychange", checkOnReturn);
});
</script>

<template>
  <header class="app-header">
    <div class="header-inner">
      <button
        class="brand"
        aria-label="Simple Transcription home"
        :disabled="uploading"
        @click="home"
      >
        <span class="brand-icon"><AudioLines :size="23" /></span>
        <span>Simple<span class="brand-light"> Transcription</span></span>
      </button>
      <div class="header-tools">
        <a
          class="wiki-link"
          :href="wiki.userGuide"
          aria-label="Help (opens in new tab)"
          target="_blank"
          rel="noopener noreferrer"
          >Help</a
        >
        <span class="local-badge"
          ><span class="status-dot" /> Your server. Your files.</span
        >
      </div>
    </div>
  </header>

  <main>
    <section
      v-if="serverUnavailable"
      class="connection-page"
      role="status"
      aria-live="polite"
    >
      <span class="connection-icon"><WifiOff :size="28" /></span>
      <p class="eyebrow">LET’S GET YOU RECONNECTED</p>
      <h1>Can’t reach your server.</h1>
      <h2>Are you connected to Tailscale?</h2>
      <p>
        Open Tailscale and check that it’s connected. If you use a local
        address, connect to your home Wi-Fi instead.
      </p>
      <p>
        Already connected? Check that your NUC is on and Simple Transcription is
        running.
      </p>
      <button
        class="button primary"
        :disabled="checkingConnection"
        @click="refresh"
      >
        <LoaderCircle v-if="checkingConnection" class="spin" :size="17" />
        {{ checkingConnection ? "Checking connection…" : "Try again" }}
      </button>
      <small
        >We can’t tell whether Tailscale is off or the server is down. Jobs
        already queued can keep running on the NUC.</small
      >
      <a
        class="wiki-link"
        :href="wiki.mobile"
        aria-label="Connection and installation help (opens in new tab)"
        target="_blank"
        rel="noopener noreferrer"
        >Connection and installation help</a
      >
      <p v-if="view !== 'history'">
        Your current page is still below. Reconnect to continue.
      </p>
    </section>
    <div v-else-if="error" class="notice error" role="alert">
      <CircleAlert :size="18" /><span
        >{{ error }}
        <button class="text-button" @click="refresh">Try again</button></span
      >
    </div>

    <template v-if="view === 'history' && !serverUnavailable">
      <InstallApp />
      <section class="page-heading">
        <div>
          <p class="eyebrow">YOUR WORDS, WRITTEN DOWN</p>
          <h1>
            Recordings in.<br class="mobile-break" />
            Transcripts out.
          </h1>
          <p class="subtitle">A little less replaying. A lot more doing.</p>
        </div>
        <button
          class="button primary new-job-button"
          :disabled="!config"
          @click="newJob"
        >
          <Plus :size="19" /> New transcription
        </button>
      </section>

      <div class="summary-strip">
        <div>
          <span class="summary-icon"><FolderOpen :size="20" /></span
          ><span
            ><strong>{{ total }}</strong
            ><small>Total jobs</small></span
          >
        </div>
        <div>
          <span class="summary-icon"><AudioLines :size="20" /></span
          ><span
            ><strong>{{ activeJobs }}</strong
            ><small>Active on this page</small></span
          >
        </div>
        <div>
          <span class="summary-icon"><CheckCircle2 :size="20" /></span
          ><span
            ><strong>{{ completedJobs }}</strong
            ><small>Ready on this page</small></span
          >
        </div>
      </div>

      <section class="history-section">
        <div class="section-heading">
          <div>
            <h2>
              Transcription history <span class="count">{{ total }}</span>
            </h2>
            <p>Everything you’ve put into words.</p>
          </div>
        </div>
        <div class="toolbar">
          <div class="tabs" aria-label="Filter jobs">
            <button
              v-for="tab in [
                { id: 'all', label: 'All jobs' },
                { id: 'active', label: 'Active' },
                { id: 'ready', label: 'Ready' },
              ]"
              :key="tab.id"
              :class="{ selected: filter === tab.id }"
              :aria-pressed="filter === tab.id"
              @click="filter = tab.id"
            >
              {{ tab.label }}
            </button>
          </div>
          <label class="search"
            ><Search :size="18" /><input
              v-model="query"
              type="search"
              placeholder="Find a job on this page"
              aria-label="Search jobs on this page"
          /></label>
        </div>
        <div v-if="loading" class="empty-state">
          <LoaderCircle class="spin" />
          <h3>Opening your library…</h3>
        </div>
        <div v-else-if="!jobs.length" class="empty-state">
          <span class="empty-icon"><FileAudio :size="30" /></span>
          <h3>Your first transcript starts here.</h3>
          <p>
            Upload an interview, a meeting, or that voice note.<br />We’ll take
            care of the words.
          </p>
          <button class="button secondary" :disabled="!config" @click="newJob">
            <Plus :size="18" /> Create a transcription
          </button>
          <div class="format-hint">
            AUDIO & VIDEO <span>→</span> TIMESTAMPED TEXT
          </div>
        </div>
        <div v-else-if="!visibleJobs.length" class="empty-state">
          <Search :size="28" />
          <h3>No matching jobs</h3>
          <p>Try a different name or filter.</p>
        </div>
        <div v-else class="job-list">
          <button
            v-for="job in visibleJobs"
            :key="job.id"
            class="job-row"
            @click="openJob(job)"
          >
            <span
              class="file-icon"
              :class="{ processing: job.status === 'processing' }"
              ><AudioLines
                v-if="job.status === 'processing'"
                :size="22" /><FileText v-else :size="22"
            /></span>
            <span class="job-main"
              ><strong>{{ job.name }}</strong
              ><span class="job-meta"
                >{{ job.files.length }}
                {{ job.files.length === 1 ? "file" : "files" }} <span>·</span>
                {{ job.model }} <span>·</span> {{ date(job.created_at) }}</span
              ></span
            >
            <span class="job-status"
              ><span class="badge" :class="job.status"
                ><LoaderCircle
                  v-if="job.status === 'processing'"
                  class="spin"
                  :size="12"
                /><Check v-else-if="job.status === 'completed'" :size="12" />{{
                  statusLabel(job)
                }}</span
              ><small v-if="active(job) && job.files.length"
                >{{ job.finished_files }} / {{ job.files.length }} files
                finished</small
              ></span
            >
            <ArrowRight class="row-arrow" :size="18" />
          </button>
        </div>
        <div v-if="total > 50" class="pagination">
          <button
            class="button secondary"
            :disabled="page === 0"
            @click="changePage(-1)"
          >
            Previous</button
          ><span>Page {{ page + 1 }} of {{ Math.ceil(total / 50) }}</span
          ><button
            class="button secondary"
            :disabled="(page + 1) * 50 >= total"
            @click="changePage(1)"
          >
            Next
          </button>
        </div>
      </section>
    </template>

    <template v-else-if="view === 'new'">
      <button class="back-button" :disabled="uploading" @click="home">
        <ArrowLeft :size="17" /> All transcriptions
      </button>
      <div class="form-layout">
        <div>
          <p class="eyebrow">MAKE ROOM FOR THE WORDS</p>
          <h1>New transcription</h1>
          <p class="subtitle">Give it a name. Drop in your recordings.</p>
          <form class="new-form" @submit.prevent="createJob">
            <fieldset :disabled="uploading">
              <label class="field-label" for="job-name">Job name</label
              ><input
                id="job-name"
                v-model="name"
                class="text-input"
                placeholder="e.g. Friday team catch-up"
                required
                maxlength="120"
                autocomplete="off"
              />
              <div class="field-heading">
                <span class="field-label">Recordings</span
                ><span>Audio or video</span>
              </div>
              <input
                ref="input"
                class="visually-hidden"
                type="file"
                multiple
                accept="audio/*,video/*,.mkv,.m4a,.mp3,.mp4,.wav,.flac,.ogg,.opus,.webm,.mov,.aac,.wma,.aiff,.amr,.3gp"
                aria-label="Choose recordings"
                @change="addFiles(($event.target as HTMLInputElement).files)"
              />
              <button
                type="button"
                class="upload-zone"
                @click="input?.click()"
                @dragover.prevent
                @drop.prevent="drop"
              >
                <span class="upload-icon"><Upload :size="24" /></span
                ><strong>Choose your recordings</strong
                ><span>or drop them here</span
                ><small
                  >Up to {{ config?.max_files }} files ·
                  {{ config ? bytes(config.max_file_bytes) : "4 GB" }} per
                  file</small
                >
              </button>
              <ul v-if="files.length" class="chosen-files">
                <li v-for="(file, index) in files" :key="index">
                  <FileAudio :size="19" /><span
                    ><strong>{{ file.name }}</strong
                    ><small>{{ bytes(file.size) }}</small></span
                  ><button
                    type="button"
                    class="icon-button"
                    :aria-label="`Remove ${file.name}`"
                    @click="files.splice(index, 1)"
                  >
                    <X :size="17" />
                  </button>
                </li>
              </ul>
              <div class="field-heading model-heading">
                <span class="field-label" id="model-label">Transcription model</span>
                <a
                  class="wiki-link"
                  :href="wiki.models"
                  aria-label="About models and speakers (opens in new tab)"
                  target="_blank"
                  rel="noopener noreferrer"
                  >About models and speakers</a
                >
              </div>
              <div
                class="model-options"
                role="radiogroup"
                aria-labelledby="model-label"
              >
                <label
                  class="model-option"
                  :class="{ checked: model === 'small' }"
                  ><input v-model="model" type="radio" value="small" /><span
                    ><strong>Small <em>RECOMMENDED</em></strong
                    ><small>A good balance of accuracy and speed.</small></span
                  ></label
                >
                <label
                  class="model-option"
                  :class="{ checked: model === 'medium' }"
                  ><input v-model="model" type="radio" value="medium" /><span
                    ><strong>Medium</strong
                    ><small
                      >More detail. A longer wait on this server.</small
                    ></span
                  ></label
                >
              </div>
              <label class="speaker-option"
                ><Users :size="20" /><span
                  ><strong>Identify speakers</strong
                  ><small>{{
                    config?.speaker_labels_available
                      ? "Add automatic speaker labels. Takes extra time."
                      : "Available after a one-time setup by your host."
                  }}</small></span
                ><input
                  v-model="diarize"
                  type="checkbox"
                  :disabled="!config?.speaker_labels_available"
              /></label>
            </fieldset>
            <div v-if="formError" class="notice error" role="alert">
              <CircleAlert :size="18" /><span>{{ formError }}</span>
            </div>
            <div v-if="uploading" class="upload-progress" role="status">
              <div>
                <strong>{{ uploadLabel }}</strong
                ><span>{{ uploadPercent }}%</span>
              </div>
              <progress
                :value="uploadPercent"
                max="100"
                aria-label="Upload progress"
              />
              <p>Keep this page open until the upload finishes.</p>
              <button type="button" class="text-button" @click="cancelUpload">
                Cancel upload
              </button>
            </div>
            <div v-else class="form-footer">
              <span
                >{{ files.length }}
                {{ files.length === 1 ? "file" : "files" }} selected<span
                  v-if="files.length"
                >
                  · {{ bytes(uploadBytes) }}</span
                ></span
              ><button
                class="button primary"
                :disabled="!files.length || !name.trim() || !config"
                type="submit"
              >
                Start transcription <ArrowRight :size="18" />
              </button>
            </div>
          </form>
        </div>
        <aside class="how-it-works">
          <span class="aside-icon"><AudioLines :size="25" /></span>
          <h2>From sound to something useful.</h2>
          <p>
            English transcripts, with timestamps and the details your next step
            needs.
          </p>
          <ol>
            <li>
              <span>1</span>
              <div>
                <strong>Upload & carry on</strong>
                <p>
                  Once uploaded, your job runs on the server. You can close this
                  page.
                </p>
              </div>
            </li>
            <li>
              <span>2</span>
              <div>
                <strong>Let it do the listening</strong>
                <p>
                  Files are processed one at a time. Long recordings can take a
                  while.
                </p>
              </div>
            </li>
            <li>
              <span>3</span>
              <div>
                <strong>Take the text with you</strong>
                <p>
                  Download a .txt for each file, or everything together as a
                  ZIP.
                </p>
              </div>
            </li>
          </ol>
          <div class="privacy-note">
            <ShieldCheck :size="19" />
            <p>
              Recordings are removed after processing. Only transcripts stay.
            </p>
          </div>
        </aside>
      </div>
    </template>

    <template v-else-if="selected">
      <button class="back-button" @click="home">
        <ArrowLeft :size="17" /> All transcriptions
      </button>
      <section class="detail-heading">
        <div>
          <p class="eyebrow">TRANSCRIPTION JOB</p>
          <h1>{{ selected.name }}</h1>
          <p class="subtitle">
            {{ date(selected.created_at) }} <span>·</span>
            {{ selected.model }} model <span>·</span> English
          </p>
        </div>
        <span class="badge" :class="selected.status">{{
          statusLabel(selected)
        }}</span>
      </section>
      <div class="detail-toolbar">
        <span
          ><FileAudio :size="18" /> {{ selected.finished_files }} of
          {{ selected.files.length }} files finished</span
        >
        <div>
          <a
            v-if="downloadable"
            class="button primary"
            :href="`/api/jobs/${selected.id}/download`"
            ><ArrowDownToLine :size="18" /> Download all</a
          ><button
            v-if="active(selected) && !selected.cancel_requested"
            class="button secondary"
            @click="confirmAction('cancel')"
          >
            Cancel job</button
          ><button
            v-if="canDelete"
            class="icon-button danger"
            aria-label="Delete job"
            @click="confirmAction('delete')"
          >
            <Trash2 :size="19" />
          </button>
        </div>
      </div>
      <nav class="detail-help" aria-label="Transcript help">
        <a
          class="wiki-link"
          :href="wiki.processing"
          aria-label="How processing works (opens in new tab)"
          target="_blank"
          rel="noopener noreferrer"
          >How processing works</a
        >
        <a
          class="wiki-link"
          :href="wiki.output"
          aria-label="About this output (opens in new tab)"
          target="_blank"
          rel="noopener noreferrer"
          >About this output</a
        >
      </nav>
      <div v-if="active(selected)" class="queue-note">
        <Clock3 :size="19" /><span>{{
          selected.status === "uploading"
            ? "This upload was not finished. Cancel the job to discard it, then create a new one."
            : "You can close this page. Your server will keep working."
        }}</span
        ><progress
          v-if="selected.status !== 'uploading'"
          :value="jobProgress(selected)"
          max="100"
          aria-label="Files finished"
        />
      </div>
      <div class="detail-files">
        <article
          v-for="file in selected.files"
          :key="file.id"
          class="file-card"
        >
          <div class="file-card-heading">
            <span class="file-icon"><FileAudio :size="22" /></span>
            <div>
              <h3>{{ file.name }}</h3>
              <p>
                {{ bytes(file.size)
                }}<span v-if="file.duration">
                  · {{ duration(file.duration) }} recording</span
                >
              </p>
            </div>
            <CheckCircle2
              v-if="file.status === 'completed'"
              class="success-icon"
              :size="22"
            /><CircleAlert
              v-else-if="file.status === 'failed'"
              class="failure-icon"
              :size="22"
            />
          </div>
          <div v-if="file.status === 'processing'" class="file-progress">
            <div>
              <strong
                ><LoaderCircle :size="15" class="spin" />
                {{ file.stage }}</strong
              ><span>{{
                file.progress !== null
                  ? `${Math.floor(file.progress)}%`
                  : "Working…"
              }}</span>
            </div>
            <progress
              :value="file.progress ?? undefined"
              max="100"
              :aria-label="file.stage"
            />
            <p v-if="file.eta_seconds !== null">
              About {{ duration(file.eta_seconds) }} left in this stage ·
              estimate
            </p>
            <p v-else>
              Progress is per stage. Model downloads and some steps take time to
              report.
            </p>
          </div>
          <p v-else class="file-stage">
            <Clock3 v-if="file.status === 'queued'" :size="15" />{{
              file.stage
            }}
          </p>
          <div v-if="file.error" class="notice error">
            <CircleAlert :size="17" /><span>{{ file.error }}</span>
          </div>
          <p
            v-for="warning in file.warnings"
            :key="warning"
            class="file-warning"
          >
            <CircleAlert :size="15" /> {{ warning }}
          </p>
          <div v-if="file.has_transcript" class="file-actions">
            <button class="button secondary" @click="showPreview(file)">
              <FileText :size="16" /> Preview</button
            ><a
              class="button secondary"
              :href="`/api/files/${file.id}/download`"
              ><ArrowDownToLine :size="16" /> .txt</a
            ><a
              class="text-button"
              :href="`/api/files/${file.id}/download?format=json`"
              >JSON <ChevronDown :size="14" /></a
            ><small v-if="file.status !== 'completed'"
              >Partial transcript</small
            >
          </div>
        </article>
      </div>
      <p class="retention-note">
        <ShieldCheck :size="17" /> Completed and failed recordings are
        automatically removed. Transcripts stay until you delete the job.
      </p>
    </template>

    <footer>
      <span><ShieldCheck :size="16" /> Processed locally. Kept private.</span
      ><span><Monitor :size="15" /> Powered by WhisperX</span>
    </footer>
  </main>

  <dialog ref="previewDialog" class="preview-dialog">
    <div class="dialog-heading">
      <div>
        <p class="eyebrow">TRANSCRIPT PREVIEW</p>
        <h2>{{ preview?.file.name }}</h2>
      </div>
      <button
        class="icon-button"
        aria-label="Close preview"
        @click="previewDialog?.close()"
      >
        <X :size="21" />
      </button>
    </div>
    <pre>{{ preview?.text }}</pre>
    <p v-if="preview?.truncated" class="file-warning">
      Preview shortened. Download the .txt for the complete transcript.
    </p>
    <div class="dialog-footer">
      <a
        v-if="preview"
        class="button primary"
        :href="`/api/files/${preview.file.id}/download`"
        ><ArrowDownToLine :size="17" /> Download .txt</a
      >
    </div>
  </dialog>
  <dialog ref="confirmDialog" class="confirm-dialog">
    <h2>
      {{ pendingAction === "delete" ? "Delete this job?" : "Cancel this job?" }}
    </h2>
    <p>
      {{
        pendingAction === "delete"
          ? "This permanently removes the job and its transcripts."
          : "Unfinished work will stop and its recordings will be removed. Any transcripts already created will stay."
      }}
    </p>
    <div class="dialog-footer">
      <button
        class="button secondary"
        :disabled="working"
        @click="confirmDialog?.close()"
      >
        Keep job</button
      ><button
        class="button destructive"
        :disabled="working"
        @click="performAction"
      >
        {{
          working
            ? "Please wait…"
            : pendingAction === "delete"
              ? "Delete job"
              : "Cancel job"
        }}
      </button>
    </div>
  </dialog>
</template>
