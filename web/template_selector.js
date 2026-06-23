import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const TEMPLATE_SELECTOR_NODE_CLASSES = new Set(["ImagenStudioTemplateSelector"]);
const STYLE_ID = "imagen-studio-template-selector-style";
const MIN_SELECTOR_NODE_WIDTH = 380;
const MIN_SELECTOR_NODE_HEIGHT = 360;
const MIN_SELECTOR_WIDGET_HEIGHT = 240;
const NODE_WIDGET_VERTICAL_OFFSET = 138;

function nodeClass(node) {
  return node?.comfyClass || node?.type || node?.constructor?.comfyClass || "";
}

function addStyles() {
  if (document.getElementById(STYLE_ID)) {
    return;
  }
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .imagen-template-selector {
      box-sizing: border-box;
      display: flex;
      flex-direction: column;
      gap: 8px;
      width: 100%;
      height: var(--imagen-selector-height, auto);
      min-height: 260px;
      padding: 8px;
      color: var(--fg-color);
      overflow: hidden;
    }
    .imagen-template-selector * {
      box-sizing: border-box;
    }
    .imagen-template-selector__bar {
      display: grid;
      grid-template-columns: minmax(120px, 1fr) auto auto;
      gap: 6px;
      align-items: center;
    }
    .imagen-template-selector input,
    .imagen-template-selector select,
    .imagen-template-selector button {
      min-height: 26px;
      border: 1px solid var(--border-color);
      border-radius: 6px;
      background: var(--comfy-input-bg);
      color: var(--input-text);
      font-size: 12px;
    }
    .imagen-template-selector input {
      width: 100%;
      padding: 4px 8px;
    }
    .imagen-template-selector button {
      padding: 3px 8px;
      cursor: pointer;
    }
    .imagen-template-selector button:hover {
      filter: brightness(1.12);
    }
    .imagen-template-selector__meta {
      display: flex;
      justify-content: space-between;
      gap: 8px;
      font-size: 11px;
      color: var(--descrip-text);
      line-height: 1.3;
    }
    .imagen-template-selector__content {
      flex: 1 1 auto;
      min-height: 170px;
      overflow-y: auto;
      padding-right: 3px;
    }
    .imagen-template-selector__grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(var(--imagen-card-min-width, 92px), 1fr));
      gap: var(--imagen-grid-gap, 8px);
    }
    .imagen-template-selector__grid.list {
      display: flex;
      flex-direction: column;
    }
    .imagen-template-card {
      border: 1px solid var(--border-color);
      border-radius: 7px;
      background: color-mix(in srgb, var(--comfy-menu-bg) 88%, black);
      cursor: pointer;
      overflow: hidden;
    }
    .imagen-template-card:hover {
      border-color: var(--fg-color);
    }
    .imagen-template-card.selected {
      border-color: #6aa9ff;
      box-shadow: 0 0 0 1px #6aa9ff inset;
    }
    .imagen-template-card__thumb {
      position: relative;
      width: 100%;
      aspect-ratio: 1 / 1;
      background: color-mix(in srgb, var(--comfy-input-bg) 78%, white);
      overflow: hidden;
    }
    .imagen-template-card__thumb img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }
    .imagen-template-card__empty {
      display: flex;
      width: 100%;
      height: 100%;
      align-items: center;
      justify-content: center;
      padding: 8px;
      color: var(--descrip-text);
      font-size: 12px;
      text-align: center;
    }
    .imagen-template-card__body {
      display: flex;
      flex-direction: column;
      gap: 3px;
      padding: 5px 6px 6px;
      min-width: 0;
    }
    .imagen-template-card__top {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 4px;
      align-items: center;
    }
    .imagen-template-card__name {
      color: var(--fg-color);
      font-size: var(--imagen-card-name-size, 12px);
      line-height: 1.25;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .imagen-template-card__actions {
      display: flex;
      gap: 3px;
      opacity: 0.88;
    }
    .imagen-template-card__actions button {
      min-height: 18px;
      padding: var(--imagen-card-action-padding, 1px 4px);
      border-radius: 4px;
      font-size: 10px;
      line-height: 1;
    }
    .imagen-template-card__actions .danger {
      color: #ffaaa8;
    }
    .imagen-template-card__category,
    .imagen-template-card__desc {
      color: var(--descrip-text);
      font-size: var(--imagen-card-meta-size, 10px);
      line-height: 1.25;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .imagen-template-selector__grid.list .imagen-template-card {
      display: grid;
      grid-template-columns: 54px minmax(0, 1fr);
      min-height: 54px;
    }
    .imagen-template-selector__grid.list .imagen-template-card__thumb {
      aspect-ratio: auto;
      height: 54px;
    }
    .imagen-template-selector[data-density="compact"] .imagen-template-card__actions {
      gap: 2px;
    }
    .imagen-template-selector[data-density="compact"] .imagen-template-card__body {
      padding: 4px 5px 5px;
    }
    .imagen-template-selector[data-density="roomy"] .imagen-template-card__body {
      gap: 4px;
      padding: 6px 7px 7px;
    }
    .imagen-template-selector__empty {
      display: flex;
      min-height: 160px;
      align-items: center;
      justify-content: center;
      border: 1px dashed var(--border-color);
      border-radius: 7px;
      color: var(--descrip-text);
      font-size: 12px;
      text-align: center;
      padding: 12px;
    }
  `;
  document.head.appendChild(style);
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) {
    node.className = className;
  }
  if (text != null) {
    node.textContent = text;
  }
  return node;
}

function findWidget(node, name) {
  return node.widgets?.find((widget) => widget?.name === name);
}

async function fetchTemplates() {
  const response = await api.fetchApi(`/imagen-studio/templates?t=${Date.now()}`);
  if (!response.ok) {
    throw new Error(`模板列表读取失败：${response.status}`);
  }
  const data = await response.json();
  return Array.isArray(data?.templates) ? data.templates : [];
}

async function renameTemplate(id, name) {
  const response = await api.fetchApi(`/imagen-studio/templates/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data?.ok === false) {
    throw new Error(data?.error || `模板改名失败：${response.status}`);
  }
  return data;
}

async function deleteTemplate(id) {
  const response = await api.fetchApi(`/imagen-studio/templates/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data?.ok === false) {
    throw new Error(data?.error || `模板删除失败：${response.status}`);
  }
  return data;
}

function matchesSearch(item, query) {
  if (!query) {
    return true;
  }
  const haystack = [
    item.id,
    item.name,
    item.categoryLabel,
    item.description,
    item.stylePromptZh,
    item.stylePromptEn,
    item.negativePrompt,
    ...(Array.isArray(item.tags) ? item.tags : []),
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(query.toLowerCase());
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function selectorWidgetHeight(node) {
  const height = Number(node?.size?.[1]) || MIN_SELECTOR_NODE_HEIGHT;
  return Math.max(MIN_SELECTOR_WIDGET_HEIGHT, Math.round(height - NODE_WIDGET_VERTICAL_OFFSET));
}

function selectorDensity(width) {
  if (width < 520) {
    return {
      name: "compact",
      cardMinWidth: 76,
      gap: 6,
      nameSize: 11,
      metaSize: 9,
      actionPadding: "1px 3px",
    };
  }
  if (width > 760) {
    return {
      name: "roomy",
      cardMinWidth: 118,
      gap: 10,
      nameSize: 12,
      metaSize: 10,
      actionPadding: "1px 5px",
    };
  }
  return {
    name: "normal",
    cardMinWidth: 94,
    gap: 8,
    nameSize: 12,
    metaSize: 10,
    actionPadding: "1px 4px",
  };
}

function setupTemplateSelector(node) {
  if (node.__imagenStudioTemplateSelector || !TEMPLATE_SELECTOR_NODE_CLASSES.has(nodeClass(node)) || typeof node.addDOMWidget !== "function") {
    return;
  }

  const idWidget = findWidget(node, "模板ID");
  if (!idWidget) {
    return;
  }

  addStyles();
  node.__imagenStudioTemplateSelector = true;

  const state = {
    templates: [],
    selectedId: String(idWidget.value || ""),
    search: "",
    category: "全部",
    mode: "grid",
    loading: false,
    error: "",
    notice: "",
  };

  const root = el("div", "imagen-template-selector");
  root.addEventListener("mousedown", (event) => event.stopPropagation());
  root.addEventListener("wheel", (event) => event.stopPropagation());

  const bar = el("div", "imagen-template-selector__bar");
  const search = document.createElement("input");
  search.placeholder = "搜索模板名称、分类、风格词";
  search.value = state.search;
  const modeButton = el("button", "", "列表");
  const refreshButton = el("button", "", "刷新");
  bar.append(search, modeButton, refreshButton);

  const meta = el("div", "imagen-template-selector__meta");
  const categorySelect = document.createElement("select");
  const status = el("span", "", "读取模板库中...");
  meta.append(categorySelect, status);

  const content = el("div", "imagen-template-selector__content");
  root.append(bar, meta, content);

  let layoutFrame = 0;
  function syncLayout() {
    const nodeWidth = Number(node.size?.[0]) || root.clientWidth || MIN_SELECTOR_NODE_WIDTH;
    const widgetHeight = selectorWidgetHeight(node);
    const density = selectorDensity(nodeWidth);
    const cardMinWidth = clamp(density.cardMinWidth, 72, Math.max(72, nodeWidth - 48));

    root.dataset.density = density.name;
    root.style.setProperty("--imagen-selector-height", `${widgetHeight}px`);
    root.style.setProperty("--imagen-card-min-width", `${cardMinWidth}px`);
    root.style.setProperty("--imagen-grid-gap", `${density.gap}px`);
    root.style.setProperty("--imagen-card-name-size", `${density.nameSize}px`);
    root.style.setProperty("--imagen-card-meta-size", `${density.metaSize}px`);
    root.style.setProperty("--imagen-card-action-padding", density.actionPadding);
  }

  function requestLayoutSync() {
    if (layoutFrame) {
      return;
    }
    layoutFrame = requestAnimationFrame(() => {
      layoutFrame = 0;
      syncLayout();
      app.graph?.setDirtyCanvas?.(true, true);
    });
  }

  function setDirty() {
    node.setDirtyCanvas?.(true, true);
    app.graph?.setDirtyCanvas?.(true, true);
    app.canvas?.setDirty?.(true, true);
  }

  function setSelected(id) {
    state.selectedId = id;
    idWidget.value = id;
    if (typeof idWidget.callback === "function") {
      idWidget.callback(id);
    }
    render();
    setDirty();
  }

  async function renameItem(item) {
    const currentName = item.name || item.id;
    const nextName = window.prompt("输入新的模板名称", currentName);
    if (nextName == null) {
      return;
    }
    const cleanName = nextName.trim();
    if (!cleanName) {
      state.notice = "模板名称不能为空";
      render();
      return;
    }
    try {
      await renameTemplate(item.id, cleanName);
      await refresh();
      state.notice = "已改名";
      render();
    } catch (error) {
      state.error = error?.message || "模板改名失败";
      render();
    }
  }

  async function deleteItem(item) {
    const name = item.name || item.id;
    if (!window.confirm(`确定删除模板“${name}”吗？此操作只删除 ComfyUI 模板库副本。`)) {
      return;
    }
    try {
      await deleteTemplate(item.id);
      if (state.selectedId === item.id) {
        setSelected("");
      }
      await refresh();
      state.notice = "已删除";
      render();
    } catch (error) {
      state.error = error?.message || "模板删除失败";
      render();
    }
  }

  const originalCallback = idWidget.callback;
  idWidget.callback = function (value) {
    state.selectedId = String(value || "");
    if (typeof originalCallback === "function") {
      originalCallback.apply(this, arguments);
    }
    render();
  };

  function filteredTemplates() {
    return state.templates.filter((item) => {
      const categoryOk = state.category === "全部" || item.categoryLabel === state.category || item.category === state.category;
      return categoryOk && matchesSearch(item, state.search);
    });
  }

  function renderCategoryOptions() {
    const current = state.category;
    const categories = ["全部", ...Array.from(new Set(state.templates.map((item) => item.categoryLabel || item.category).filter(Boolean)))];
    categorySelect.innerHTML = "";
    for (const category of categories) {
      const option = document.createElement("option");
      option.value = category;
      option.textContent = category;
      categorySelect.appendChild(option);
    }
    state.category = categories.includes(current) ? current : "全部";
    categorySelect.value = state.category;
  }

  function renderCard(item) {
    const card = el("div", `imagen-template-card${item.id === state.selectedId ? " selected" : ""}`);
    card.title = `${item.name || item.id}\n${item.stylePromptZh || item.stylePromptEn || ""}`;
    card.onclick = () => setSelected(item.id);

    const thumb = el("div", "imagen-template-card__thumb");
    if (item.thumbnailUrl) {
      const image = document.createElement("img");
      image.loading = "lazy";
      image.src = item.thumbnailUrl;
      image.alt = item.name || item.id;
      image.onerror = () => {
        thumb.innerHTML = "";
        thumb.appendChild(el("div", "imagen-template-card__empty", "无预览"));
      };
      thumb.appendChild(image);
    } else {
      thumb.appendChild(el("div", "imagen-template-card__empty", "无预览"));
    }

    const body = el("div", "imagen-template-card__body");
    const top = el("div", "imagen-template-card__top");
    top.appendChild(el("div", "imagen-template-card__name", item.name || item.id));
    const actions = el("div", "imagen-template-card__actions");
    const renameButton = el("button", "", "改名");
    renameButton.title = "修改模板名称";
    renameButton.onclick = (event) => {
      event.stopPropagation();
      renameItem(item);
    };
    const deleteButton = el("button", "danger", "删除");
    deleteButton.title = "删除此模板";
    deleteButton.onclick = (event) => {
      event.stopPropagation();
      deleteItem(item);
    };
    actions.append(renameButton, deleteButton);
    top.appendChild(actions);
    body.appendChild(top);
    body.appendChild(el("div", "imagen-template-card__category", item.categoryLabel || item.category || "模板"));
    body.appendChild(el("div", "imagen-template-card__desc", item.description || item.stylePromptZh || item.stylePromptEn || ""));
    card.append(thumb, body);
    return card;
  }

  function render() {
    syncLayout();
    renderCategoryOptions();
    const items = filteredTemplates();
    modeButton.textContent = state.mode === "grid" ? "列表" : "网格";
    if (state.loading) {
      status.textContent = "读取模板库中...";
    } else if (state.error) {
      status.textContent = state.error;
    } else if (state.notice) {
      status.textContent = state.notice;
    } else {
      status.textContent = `共 ${state.templates.length} 个，显示 ${items.length} 个`;
    }

    content.innerHTML = "";
    if (state.error) {
      content.appendChild(el("div", "imagen-template-selector__empty", state.error));
      requestLayoutSync();
      return;
    }
    if (!items.length) {
      content.appendChild(el("div", "imagen-template-selector__empty", "暂无模板。先用“Imagen Studio 模板入库”节点保存一个模板。"));
      requestLayoutSync();
      return;
    }
    const grid = el("div", `imagen-template-selector__grid${state.mode === "list" ? " list" : ""}`);
    for (const item of items) {
      grid.appendChild(renderCard(item));
    }
    content.appendChild(grid);
    requestLayoutSync();
  }

  async function refresh() {
    state.loading = true;
    state.error = "";
    state.notice = "";
    render();
    try {
      state.templates = await fetchTemplates();
      if (state.selectedId && !state.templates.some((item) => item.id === state.selectedId)) {
        state.notice = `当前模板ID不存在：${state.selectedId}`;
      }
    } catch (error) {
      state.error = error?.message || "模板列表读取失败";
    } finally {
      state.loading = false;
      render();
    }
  }

  search.oninput = () => {
    state.search = search.value;
    render();
  };
  categorySelect.onchange = () => {
    state.category = categorySelect.value;
    render();
  };
  modeButton.onclick = () => {
    state.mode = state.mode === "grid" ? "list" : "grid";
    render();
  };
  refreshButton.onclick = () => refresh();

  const selectorWidget = node.addDOMWidget("模板选择器", "imagen-template-selector", root, {
    serialize: false,
    hideOnZoom: false,
    getMinHeight: () => MIN_SELECTOR_WIDGET_HEIGHT,
    getMaxHeight: () => selectorWidgetHeight(node),
  });

  const originalOnResize = node.onResize;
  node.onResize = function (...args) {
    const result = originalOnResize?.apply(this, args);
    requestLayoutSync();
    return result;
  };

  if (typeof ResizeObserver !== "undefined") {
    const observer = new ResizeObserver(() => requestLayoutSync());
    observer.observe(root);
    node.__imagenStudioTemplateSelectorResizeObserver = observer;
  }

  if ((node.size?.[0] || 0) < MIN_SELECTOR_NODE_WIDTH || (node.size?.[1] || 0) < MIN_SELECTOR_NODE_HEIGHT) {
    node.setSize?.([Math.max(node.size?.[0] || 0, MIN_SELECTOR_NODE_WIDTH), Math.max(node.size?.[1] || 0, MIN_SELECTOR_NODE_HEIGHT)]);
  }

  syncLayout();
  refresh();
}

function setupSoon(node) {
  setupTemplateSelector(node);
  requestAnimationFrame(() => setupTemplateSelector(node));
}

app.registerExtension({
  name: "ImagenStudio.TemplateSelector",
  nodeCreated(node) {
    setupSoon(node);
  },
  loadedGraphNode(node) {
    setupSoon(node);
  },
});
