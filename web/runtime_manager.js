import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const EXTENSION_NAME = "kktools.RuntimeManager";
const REFRESH_INTERVAL = 2000;
const STYLE_ID = "kktools-runtime-manager-style";

let monitor;
let refreshTimer;
let refreshing = false;
let magneticDockActive = false;

function addStyles() {
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .kk-runtime-manager {
      box-sizing: border-box;
      display: flex;
      align-items: center;
      gap: 8px;
      height: auto;
      min-width: 520px;
      padding: 6px;
      color: var(--input-text, #ddd);
      background: var(--comfy-menu-bg, #202020);
      border: 0 !important;
      border-radius: 10px;
      outline: none !important;
      box-shadow: none !important;
      font: 14px/1.2 Inter, system-ui, sans-serif;
      white-space: nowrap;
      cursor: pointer;
      user-select: none;
    }
    .kk-runtime-manager:focus,
    .kk-runtime-manager:focus-visible {
      outline: none !important;
      box-shadow: none !important;
    }
    .kk-runtime-manager__title {
      display: flex;
      align-items: center;
      gap: 7px;
      flex: none;
      align-self: stretch;
      padding: 0 12px;
      border-radius: 8px;
      background: var(--comfy-input-bg, #292929);
      font-size: 15px;
      font-weight: 650;
    }
    .kk-runtime-manager__title::before {
      content: "";
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: #55c878;
      box-shadow: 0 0 7px rgba(85, 200, 120, .65);
    }
    .kk-runtime-manager.is-error .kk-runtime-manager__title::before {
      background: #dc6b6b;
      box-shadow: 0 0 7px rgba(220, 107, 107, .65);
    }
    .kk-runtime-manager__metrics {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, auto));
      align-items: center;
      gap: 8px;
      min-width: 0;
    }
    .kk-runtime-manager__metric {
      position: relative;
      overflow: hidden;
      padding: 8px 10px;
      border-radius: 8px;
      background: var(--comfy-input-bg, #292929);
      font-variant-numeric: tabular-nums;
    }
    .kk-runtime-manager__metric::before {
      content: "";
      position: absolute;
      inset: auto 0 0;
      height: 3px;
      width: var(--usage, 0%);
      background: var(--usage-color, #55c878);
      transition: width .3s ease;
    }
    .kk-runtime-manager__metric b { color: var(--descrip-text, #999); font-weight: 500; }
    .kk-runtime-manager__metric span { margin-left: 3px; }
    .kk-runtime-dockzone {
      position: relative !important;
      transition: transform .16s ease, border-color .16s ease, box-shadow .16s ease;
    }
    @media (max-width: 1450px) {
      .kk-runtime-manager { min-width: 0; }
      .kk-runtime-manager__title span { display: none; }
    }
    @media (max-width: 1180px) {
      .kk-runtime-manager__metric[data-key="gpu"] { display: none; }
      .kk-runtime-manager__metrics { grid-template-columns: repeat(3, minmax(0, auto)); }
    }
    @media (max-width: 980px) {
      .kk-runtime-manager { display: none; }
    }
  `;
  document.head.appendChild(style);
}

function usageColor(percent) {
  if (percent >= 90) return "#e06565";
  if (percent >= 70) return "#dfaa4d";
  return "#55c878";
}

function formatPercent(value) {
  return Number.isFinite(value) ? `${Math.round(value)}%` : "--";
}

function formatBytes(value) {
  if (!Number.isFinite(value)) return "--";
  const gib = value / 1073741824;
  return `${gib >= 10 ? gib.toFixed(0) : gib.toFixed(1)}G`;
}

function setMetric(key, value, percent, title = "") {
  const item = monitor?.querySelector(`[data-key="${key}"]`);
  if (!item) return;
  item.querySelector("span").textContent = value;
  item.style.setProperty("--usage", Number.isFinite(percent) ? `${percent}%` : "0%");
  item.style.setProperty("--usage-color", usageColor(percent));
  item.title = title;
}

function createMonitor() {
  const element = document.createElement("div");
  element.className = "kk-runtime-manager";
  element.setAttribute("aria-label", "运行管理：查看 CPU、内存、GPU 和显存使用情况");
  element.innerHTML = `
    <div class="kk-runtime-manager__title"><span>运行管理</span></div>
    <div class="kk-runtime-manager__metrics">
      <div class="kk-runtime-manager__metric" data-key="cpu"><b>CPU</b><span>--</span></div>
      <div class="kk-runtime-manager__metric" data-key="memory"><b>内存</b><span>--</span></div>
      <div class="kk-runtime-manager__metric" data-key="gpu"><b>GPU</b><span>--</span></div>
      <div class="kk-runtime-manager__metric" data-key="vram"><b>显存</b><span>--</span></div>
    </div>
  `;
  const refresh = () => void refreshStats(true);
  element.addEventListener("click", refresh);
  return element;
}

function mountMonitor() {
  const actionbar = document.querySelector(".actionbar-container");
  if (!actionbar || !monitor) return;
  if (monitor.parentElement !== actionbar) {
    actionbar.insertBefore(monitor, actionbar.firstElementChild);
  }
  syncDockzoneLabel(actionbar);
}

function syncDockzoneLabel(actionbar) {
  const panel = actionbar.querySelector(".actionbar");
  const actionbarRoot = panel?.parentElement;
  if (!panel || !actionbarRoot) return;

  const dropzone = [...actionbarRoot.children]
    .find((element) => element !== panel && element.textContent.trim());
  if (!dropzone) {
    magneticDockActive = false;
    return;
  }
  dropzone.classList.add("kk-runtime-dockzone");
  if (dropzone.textContent.trim() !== "停靠到显存右侧") {
    dropzone.textContent = "停靠到显存右侧";
  }
}

function updateMagneticDock(event) {
  const dropzone = document.querySelector(".kk-runtime-dockzone");
  if (!dropzone) {
    magneticDockActive = false;
    return;
  }

  const monitorBottom = monitor?.getBoundingClientRect().bottom || 100;
  const nearTop = event.clientY <= Math.max(180, monitorBottom + 72);
  if (nearTop === magneticDockActive) return;
  magneticDockActive = nearTop;
  dropzone.dispatchEvent(new MouseEvent(nearTop ? "mouseenter" : "mouseleave", {
    view: window,
    clientX: event.clientX,
    clientY: event.clientY,
  }));
}

async function refreshStats(force = false) {
  if (refreshing || (!force && document.hidden)) return;
  refreshing = true;
  try {
    const response = await api.fetchApi(`/kktools/runtime_stats?t=${Date.now()}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    if (!payload.ok) throw new Error(payload.error || "运行状态读取失败");

    const { cpu, memory, process, devices } = payload.data;
    const gpu = devices?.[0];
    const memoryUsed = memory.total - memory.available;
    setMetric("cpu", formatPercent(cpu.percent), cpu.percent, `${cpu.logical_cores || "--"} 个逻辑核心`);
    setMetric(
      "memory",
      `${formatBytes(memoryUsed)}/${formatBytes(memory.total)}`,
      memory.percent,
      `系统内存 ${formatPercent(memory.percent)} · ComfyUI ${formatBytes(process.memory_used)}`,
    );
    setMetric(
      "gpu",
      gpu ? (Number.isFinite(gpu.utilization) ? formatPercent(gpu.utilization) : String(gpu.type).toUpperCase()) : "无",
      gpu?.utilization,
      gpu?.name || "未检测到 GPU",
    );
    setMetric(
      "vram",
      gpu ? `${formatBytes(gpu.memory_used)}/${formatBytes(gpu.memory_total)}` : "--",
      gpu?.memory_percent,
      gpu ? `显存 ${formatPercent(gpu.memory_percent)}` : "未检测到显存",
    );
    monitor.classList.remove("is-error");
    monitor.title = "点击立即刷新运行状态";
  } catch (error) {
    monitor?.classList.add("is-error");
    if (monitor) monitor.title = `运行状态读取失败：${error.message}`;
  } finally {
    refreshing = false;
  }
}

app.registerExtension({
  name: EXTENSION_NAME,
  async setup() {
    addStyles();
    monitor = createMonitor();
    mountMonitor();

    const observer = new MutationObserver(mountMonitor);
    observer.observe(document.body, { childList: true, subtree: true });
    window.addEventListener("beforeunload", () => observer.disconnect(), { once: true });
    window.addEventListener("mousemove", updateMagneticDock, { passive: true });
    window.addEventListener("beforeunload", () => {
      window.removeEventListener("mousemove", updateMagneticDock);
    }, { once: true });

    await refreshStats(true);
    refreshTimer = window.setInterval(refreshStats, REFRESH_INTERVAL);
    window.addEventListener("beforeunload", () => window.clearInterval(refreshTimer), { once: true });
  },
});
