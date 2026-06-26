/**
 * kktools Settings Panel Extension
 * Registers a custom settings UI in ComfyUI settings dialog.
 * Supports: imagen_studio and runninghub API configuration with test & model fetch.
 */

import { app } from "../../scripts/app.js";
import { $el } from "../../scripts/ui.js";

const EXT_NAME = "kktools.Settings";
const API_BASE = ""; // relative, proxied through ComfyUI

// ─── API helpers ────────────────────────────────────────────────────────────

async function apiGet(path) {
  const resp = await fetch(path.startsWith("/") ? path : `/${path}`, {
    credentials: "include",
  });
  const data = await resp.json();
  return data;
}

async function apiPost(path, body) {
  const resp = await fetch(path.startsWith("/") ? path : `/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    credentials: "include",
  });
  const data = await resp.json();
  return data;
}

// ─── State ──────────────────────────────────────────────────────────────────

let _settingsLoaded = false;
let _settingsData = null;

// ─── DOM element helpers ────────────────────────────────────────────────────

function getEl(selector) {
  return document.querySelector(selector);
}

function showStatus(el, message, type = "success") {
  el.textContent = message;
  el.className = `kktools-status visible ${type}`;
}

function hideStatus(el) {
  el.className = "kktools-status";
}

function setLoading(btn, text, loading) {
  if (!btn) return;
  btn.disabled = loading;
  btn.textContent = loading ? text + "..." : text;
}

function setConfigPath(path) {
  const el = getEl("#kk-config-path");
  if (!el) return;
  el.textContent = path || "未找到同步路径";
  el.title = path || "";
}

function ensureSelectOption(select, value, labelSuffix = "已保存") {
  if (!select || !value) return;
  const exists = Array.from(select.options).some((option) => option.value === value);
  if (exists) return;
  const opt = document.createElement("option");
  opt.value = value;
  opt.textContent = `${value}（${labelSuffix}）`;
  select.appendChild(opt);
}

function replaceSelectOptions(select, models, selectedValue = "") {
  if (!select) return;
  models = models || [];
  select.innerHTML = "";
  if (!models || models.length === 0) {
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "请先拉取模型或手动填写";
    select.appendChild(placeholder);
  }
  models.forEach((m) => {
    const opt = document.createElement("option");
    opt.value = m;
    opt.textContent = m;
    select.appendChild(opt);
  });
  ensureSelectOption(select, selectedValue);
  select.value = selectedValue || select.options[0]?.value || "";
}

function renderModelTags(container, models) {
  container.innerHTML = "";
  const label = document.createElement("div");
  label.className = "kktools-model-list-label";
  label.textContent = `${models.length} 个可用模型：`;
  container.appendChild(label);
  const tagsWrap = document.createElement("div");
  tagsWrap.className = "kktools-model-tags";
  models.forEach((m) => {
    const tag = document.createElement("span");
    tag.className = "kktools-model-tag";
    tag.textContent = m;
    tag.title = `点击复制: ${m}`;
    tag.onclick = () => {
      navigator.clipboard?.writeText(m).catch(() => {});
      tag.style.background = "rgba(119,55,170,0.5)";
      setTimeout(() => {
        tag.style.background = "";
      }, 300);
    };
    tagsWrap.appendChild(tag);
  });
  container.appendChild(tagsWrap);
  container.classList.add("visible");
}

// ─── Form binding helpers ───────────────────────────────────────────────────

function bindInputToggle(btn, input) {
  if (!btn || !input) return;
  btn.addEventListener("click", () => {
    const isPassword = input.type === "password";
    input.type = isPassword ? "text" : "password";
    btn.textContent = isPassword ? "👁" : "🔒";
  });
}

async function loadSettingsToForm(form) {
  if (_settingsLoaded) return;
  try {
    const result = await apiGet("kktools/settings");
    if (result.ok) {
      _settingsData = result.data;
      _settingsLoaded = true;
      setConfigPath(result.configPath || "");
      // imagen_studio
      const is1 = _settingsData;
      const imApiKey = getEl("#kk-is-apikey");
      const imBaseUrl = getEl("#kk-is-baseurl");
      const imVision = getEl("#kk-is-vision");
      const imText = getEl("#kk-is-text");
      if (imApiKey) imApiKey.value = is1.apiKey || "";
      if (imBaseUrl) imBaseUrl.value = is1.baseUrl || "";
      ensureSelectOption(imVision, is1.visionModel);
      ensureSelectOption(imText, is1.textModel);
      if (imVision) imVision.value = is1.visionModel || "";
      if (imText) imText.value = is1.textModel || "";
      // runninghub
      const rhApiKey = getEl("#kk-rh-apikey");
      const rhBaseUrl = getEl("#kk-rh-baseurl");
      if (rhApiKey) rhApiKey.value = is1.runninghubApiKey || "";
      if (rhBaseUrl) rhBaseUrl.value = is1.runninghubBaseUrl || "";
    }
  } catch (e) {
    console.warn("[kktools.Settings] Failed to load settings:", e);
  }
}

async function saveSettings(form) {
  const data = {
    apiKey: (getEl("#kk-is-apikey")?.value || "").trim(),
    baseUrl: (getEl("#kk-is-baseurl")?.value || "").trim(),
    visionModel: (getEl("#kk-is-vision")?.value || "").trim(),
    textModel: (getEl("#kk-is-text")?.value || "").trim(),
    runninghubApiKey: (getEl("#kk-rh-apikey")?.value || "").trim(),
    runninghubBaseUrl: (getEl("#kk-rh-baseurl")?.value || "").trim(),
  };
  const result = await apiPost("kktools/settings", data);
  if (result.ok) {
    setConfigPath(result.configPath || getEl("#kk-config-path")?.textContent || "");
    _settingsLoaded = false; // force reload
    _settingsData = null;
    const savedBadge = getEl("#kk-saved-badge");
    if (savedBadge) {
      savedBadge.classList.add("visible");
      setTimeout(() => savedBadge.classList.remove("visible"), 3000);
    }
  } else {
    const errEl = getEl("#kk-global-status");
    showStatus(errEl, `保存失败：${result.error || "未知错误"}`, "error");
  }
  return result;
}

// ─── Test & Model fetch ─────────────────────────────────────────────────────

async function testImagenStudio(btn) {
  setLoading(btn, "测试连接", true);
  const statusEl = getEl("#kk-is-status");
  hideStatus(statusEl);
  try {
    const result = await apiPost("kktools/settings/imagen_studio/test", {});
    if (result.ok) {
      showStatus(statusEl, `✅ ${result.message}`, "success");
    } else {
      showStatus(statusEl, `❌ ${result.error || "连接失败"}`, "error");
    }
  } catch (e) {
    showStatus(statusEl, `❌ 网络错误：${e.message}`, "error");
  } finally {
    setLoading(btn, "测试连通性", false);
  }
}

async function testRunningHub(btn) {
  setLoading(btn, "测试连接", true);
  const statusEl = getEl("#kk-rh-status");
  hideStatus(statusEl);
  try {
    const result = await apiPost("kktools/settings/runninghub/test", {});
    if (result.ok) {
      showStatus(statusEl, `✅ ${result.message}`, "success");
    } else {
      showStatus(statusEl, `❌ ${result.error || "连接失败"}`, "error");
    }
  } catch (e) {
    showStatus(statusEl, `❌ 网络错误：${e.message}`, "error");
  } finally {
    setLoading(btn, "测试连通性", false);
  }
}

async function fetchModelsImagenStudio(btn) {
  setLoading(btn, "拉取模型", true);
  const statusEl = getEl("#kk-is-status");
  const modelList = getEl("#kk-is-models");
  hideStatus(statusEl);
  modelList?.classList.remove("visible");
  try {
    const result = await apiGet("kktools/settings/imagen_studio/models");
    if (result.ok && result.models && result.models.length > 0) {
      showStatus(statusEl, `✅ 找到 ${result.models.length} 个模型`, "success");
      if (modelList) renderModelTags(modelList, result.models);
      // Also populate selects
      const visionSelect = getEl("#kk-is-vision");
      const textSelect = getEl("#kk-is-text");
      replaceSelectOptions(visionSelect, result.models, _settingsData?.visionModel || visionSelect?.value || "");
      replaceSelectOptions(textSelect, result.models, _settingsData?.textModel || textSelect?.value || "");
    } else {
      showStatus(statusEl, `⚠️ ${result.error || "未找到模型"}`, "warning");
    }
  } catch (e) {
    showStatus(statusEl, `❌ 网络错误：${e.message}`, "error");
  } finally {
    setLoading(btn, "拉取模型列表", false);
  }
}

async function fetchModelsRunningHub(btn) {
  setLoading(btn, "拉取模型", true);
  const statusEl = getEl("#kk-rh-status");
  const modelList = getEl("#kk-rh-models");
  hideStatus(statusEl);
  modelList?.classList.remove("visible");
  try {
    const result = await apiGet("kktools/settings/runninghub/models");
    if (result.ok && result.models && result.models.length > 0) {
      showStatus(statusEl, `✅ 找到 ${result.models.length} 个模型`, "success");
      if (modelList) renderModelTags(modelList, result.models);
    } else {
      showStatus(statusEl, `⚠️ ${result.error || "未找到模型"}`, "warning");
    }
  } catch (e) {
    showStatus(statusEl, `❌ 网络错误：${e.message}`, "error");
  } finally {
    setLoading(btn, "拉取模型列表", false);
  }
}

// ─── Build settings panel HTML ───────────────────────────────────────────────

function buildSettingsPanel() {
  const panel = document.createElement("div");
  panel.className = "kktools-settings-panel";

  // Title
  const title = document.createElement("div");
  title.className = "kktools-settings-title";
  title.innerHTML = '<span class="icon">🌟</span><span>kktools 设置</span>';
  panel.appendChild(title);

  const syncInfo = document.createElement("div");
  syncInfo.className = "kktools-sync-info";
  syncInfo.innerHTML = `
    <span class="kktools-sync-label">同步文件</span>
    <code id="kk-config-path">加载中...</code>`;
  panel.appendChild(syncInfo);

  // ── Section 1: Imagen Studio ────────────────────────────────────────────
  const sec1 = document.createElement("div");
  sec1.className = "kktools-section";
  sec1.innerHTML = '<div class="kktools-section-title">🖼️ 图像工作室</div>';

  // API Key
  sec1.appendChild(makeFormRow("API Key", `
    <div class="kktools-input-wrap">
      <input id="kk-is-apikey" type="password" class="kktools-input has-toggle"
        placeholder="填写后点击测试验证连通性"
        autocomplete="new-password" />
      <button id="kk-is-apikey-toggle" class="kktools-pw-toggle" type="button" title="显示/隐藏">👁</button>
    </div>`));

  // Base URL
  sec1.appendChild(makeFormRow("Base URL", `
    <div class="kktools-input-wrap full">
      <input id="kk-is-baseurl" type="text" class="kktools-input"
        placeholder="https://api.zuco.ai/v1 或第三方兼容地址"
        value="https://api.zuco.ai/v1" />
    </div>`));

  // Vision Model
  sec1.appendChild(makeFormRow("Vision Model", `
    <div class="kktools-input-wrap full">
      <select id="kk-is-vision" class="kktools-select">
        <option value="">请先拉取模型或手动填写</option>
      </select>
    </div>`));

  // Text Model
  sec1.appendChild(makeFormRow("Text Model", `
    <div class="kktools-input-wrap full">
      <select id="kk-is-text" class="kktools-select">
        <option value="">请先拉取模型或手动填写</option>
      </select>
    </div>`));

  // IS Buttons
  const isBtnRow = document.createElement("div");
  isBtnRow.className = "kktools-btn-row";
  isBtnRow.innerHTML = `
    <button id="kk-is-test" class="kktools-btn" type="button">🔗 测试连通性</button>
    <button id="kk-is-models-btn" class="kktools-btn kktools-btn-secondary" type="button">📋 拉取模型列表</button>
    <button id="kk-is-save" class="kktools-btn" type="button">💾 保存配置</button>`;
  sec1.appendChild(isBtnRow);

  // IS Status
  const isStatus = document.createElement("div");
  isStatus.id = "kk-is-status";
  isStatus.className = "kktools-status";
  sec1.appendChild(isStatus);

  // IS Model List
  const isModels = document.createElement("div");
  isModels.id = "kk-is-models";
  isModels.className = "kktools-model-list";
  sec1.appendChild(isModels);

  panel.appendChild(sec1);

  // ── Section 2: RunningHub ────────────────────────────────────────────────
  const sec2 = document.createElement("div");
  sec2.className = "kktools-section";
  sec2.innerHTML = '<div class="kktools-section-title">🚀 RunningHub</div>';

  // RH API Key
  sec2.appendChild(makeFormRow("API Key", `
    <div class="kktools-input-wrap">
      <input id="kk-rh-apikey" type="password" class="kktools-input has-toggle"
        placeholder="RunningHub API Key"
        autocomplete="new-password" />
      <button id="kk-rh-apikey-toggle" class="kktools-pw-toggle" type="button" title="显示/隐藏">👁</button>
    </div>`));

  // RH Base URL
  sec2.appendChild(makeFormRow("Base URL", `
    <div class="kktools-input-wrap full">
      <input id="kk-rh-baseurl" type="text" class="kktools-input"
        placeholder="https://www.runninghub.cn/openapi/v2"
        value="https://www.runninghub.cn/openapi/v2" />
    </div>`));

  // RH Buttons
  const rhBtnRow = document.createElement("div");
  rhBtnRow.className = "kktools-btn-row";
  rhBtnRow.innerHTML = `
    <button id="kk-rh-test" class="kktools-btn" type="button">🔗 测试连通性</button>
    <button id="kk-rh-models-btn" class="kktools-btn kktools-btn-secondary" type="button">📋 拉取模型列表</button>
    <button id="kk-rh-save" class="kktools-btn" type="button">💾 保存配置</button>`;
  sec2.appendChild(rhBtnRow);

  // RH Status
  const rhStatus = document.createElement("div");
  rhStatus.id = "kk-rh-status";
  rhStatus.className = "kktools-status";
  sec2.appendChild(rhStatus);

  // RH Model List
  const rhModels = document.createElement("div");
  rhModels.id = "kk-rh-models";
  rhModels.className = "kktools-model-list";
  sec2.appendChild(rhModels);

  panel.appendChild(sec2);

  // ── Global Save & Status ────────────────────────────────────────────────
  const globalRow = document.createElement("div");
  globalRow.style.cssText = "display:flex;align-items:center;gap:12px;margin-top:8px;";
  globalRow.innerHTML = `
    <button id="kk-save-all" class="kktools-btn" type="button"
      style="background:#9B59c9;font-size:13px;padding:9px 18px;">💾 保存全部配置</button>
    <span id="kk-saved-badge" class="kktools-saved-badge">✅ 已保存</span>`;
  panel.appendChild(globalRow);

  const globalStatus = document.createElement("div");
  globalStatus.id = "kk-global-status";
  globalStatus.className = "kktools-status";
  panel.appendChild(globalStatus);

  // ── Wire up events ──────────────────────────────────────────────────────
  setTimeout(() => {
    // Password toggles
    bindInputToggle(getEl("#kk-is-apikey-toggle"), getEl("#kk-is-apikey"));
    bindInputToggle(getEl("#kk-rh-apikey-toggle"), getEl("#kk-rh-apikey"));

    // Imagen Studio buttons
    getEl("#kk-is-test")?.addEventListener("click", (e) => testImagenStudio(e.target));
    getEl("#kk-is-models-btn")?.addEventListener("click", (e) => fetchModelsImagenStudio(e.target));
    getEl("#kk-is-save")?.addEventListener("click", async (e) => {
      setLoading(e.target, "保存中", true);
      await saveSettings();
      setLoading(e.target, "💾 保存配置", false);
    });

    // RunningHub buttons
    getEl("#kk-rh-test")?.addEventListener("click", (e) => testRunningHub(e.target));
    getEl("#kk-rh-models-btn")?.addEventListener("click", (e) => fetchModelsRunningHub(e.target));
    getEl("#kk-rh-save")?.addEventListener("click", async (e) => {
      setLoading(e.target, "保存中", true);
      await saveSettings();
      setLoading(e.target, "💾 保存配置", false);
    });

    // Global save
    getEl("#kk-save-all")?.addEventListener("click", async (e) => {
      setLoading(e.target, "保存中", true);
      await saveSettings();
      setLoading(e.target, "💾 保存全部配置", false);
    });

    // Auto-load settings when panel is shown
    loadSettingsToForm();
  }, 0);

  return panel;
}

function makeFormRow(labelText, inputHtml) {
  const row = document.createElement("div");
  row.className = "kktools-form-row";
  const label = document.createElement("label");
  label.className = "kktools-label";
  label.textContent = labelText;
  const wrap = document.createElement("div");
  wrap.className = "kktools-input-wrap full";
  wrap.innerHTML = inputHtml;
  row.appendChild(label);
  row.appendChild(wrap);
  return row;
}

// ─── CSS injection ───────────────────────────────────────────────────────────

let _cssLoaded = false;
function loadCss() {
  if (_cssLoaded) return;
  _cssLoaded = true;
  const id = "kktools-settings-panel-css";
  if (document.getElementById(id)) return;
  const link = document.createElement("link");
  link.id = id;
  link.rel = "stylesheet";
  link.href = new URL("kktools_settings.css", import.meta.url).href;
  document.head.appendChild(link);
}

// ─── Extension ───────────────────────────────────────────────────────────────

const settingId = "kktools.SettingsPanel";

const ext = {
  name: EXT_NAME,

  async setup() {
    loadCss();

    // Wait a tick for app.ui.settings to be ready
    await new Promise((r) => setTimeout(r, 100));

    app.ui.settings.addSetting({
      id: settingId,
      name: "🌟 kktools 设置面板",
      category: ["kktools", "Settings"],
      defaultValue: "",
      type: () => {
        return $el("div.kktools-settings-host", [buildSettingsPanel()]);
      },
      onChange() {
        // Re-load settings when settings dialog opens
        _settingsLoaded = false;
        _settingsData = null;
        setTimeout(() => loadSettingsToForm(), 200);
      },
    });
  },
};

app.registerExtension(ext);
