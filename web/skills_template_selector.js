import { app } from "/scripts/app.js";
import { api } from "/scripts/api.js";

const NODE_CLASS = "kkSkills模板选择器";
const SKILL_TABS = [
  { id: "", label: "全部" },
  { id: "图像", label: "图像" },
  { id: "视频", label: "视频" },
  { id: "文案", label: "文案" },
  { id: "其他", label: "其他" },
];
const SKILL_TAB_ALIASES = new Map([
  ["图像", ["图像", "图片", "绘画", "摄影", "设计"]],
  ["视频", ["视频", "短视频", "动画"]],
  ["文案", ["文案", "文本", "写作", "提示词"]],
]);

function skillTab(item) {
  const tag = String(item?.tag || "").trim().toLowerCase();
  if (!tag) return "其他";
  for (const [tab, aliases] of SKILL_TAB_ALIASES) {
    if (aliases.includes(tag)) return tab;
  }
  return "其他";
}

function addStyles() {
  if (document.getElementById("kk-skills-selector-style")) return;
  const style = document.createElement("style");
  style.id = "kk-skills-selector-style";
  style.textContent = `
    .kk-skills-selector { display:flex; flex-direction:column; gap:8px; width:100%; height:100%; min-height:300px; padding:8px; box-sizing:border-box; color:var(--fg-color); }
    .kk-skills-selector * { box-sizing:border-box; }
    .kk-skills-selector__bar { display:flex; flex-wrap:wrap; gap:6px; }
    .kk-skills-selector input,.kk-skills-selector button { min-height:26px; border:1px solid var(--border-color); border-radius:6px; background:var(--comfy-input-bg); color:var(--input-text); }
    .kk-skills-selector input { flex:1 1 180px; width:100%; padding:4px 8px; }
    .kk-skills-selector button { padding:3px 7px; cursor:pointer; }
    .kk-skills-selector__status { color:var(--descrip-text); font-size:11px; }
    .kk-skills-selector__status:empty { display:none; }
    .kk-skills-selector__tabs { display:flex; gap:3px; overflow-x:auto; border-bottom:1px solid var(--border-color); scrollbar-width:thin; }
    .kk-skills-selector__tabs button { flex:0 0 auto; min-height:28px; padding:3px 8px; border:0; border-bottom:2px solid transparent; border-radius:6px 6px 0 0; background:transparent; color:var(--descrip-text); font-size:11px; }
    .kk-skills-selector__tabs button:hover { background:rgba(106,169,255,.1); color:var(--fg-color); }
    .kk-skills-selector__tabs button:focus-visible { outline:2px solid #6aa9ff; outline-offset:-2px; }
    .kk-skills-selector__tabs button.selected { border-bottom-color:#6aa9ff; background:rgba(106,169,255,.16); color:#c5ddff; }
    .kk-skills-selector__content { flex:1; min-height:180px; overflow-y:auto; }
    .kk-skills-selector__grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(100px,1fr)); gap:8px; }
    .kk-skill-card { position:relative; overflow:hidden; border:1px solid var(--border-color); border-radius:7px; background:var(--comfy-menu-bg); cursor:pointer; }
    .kk-skill-card.selected { border-color:#6aa9ff; box-shadow:0 0 0 1px #6aa9ff inset; }
    .kk-skill-card__cover { display:flex; align-items:center; justify-content:center; width:100%; aspect-ratio:16/10; overflow:hidden; background:var(--comfy-input-bg); color:var(--descrip-text); font-size:11px; }
    .kk-skill-card__cover img { width:100%; height:100%; object-fit:cover; }
    .kk-skill-card__body { position:relative; padding:6px; }
    .kk-skill-card__name { overflow:hidden; color:var(--fg-color); font-size:12px; font-weight:600; white-space:nowrap; text-overflow:ellipsis; }
    .kk-skill-card__tag-row { display:flex; align-items:center; gap:4px; min-width:0; margin-top:4px; }
    .kk-skill-card__tag { display:inline-block; min-width:0; max-width:100%; padding:2px 5px; overflow:hidden; border-radius:4px; background:rgba(106,169,255,.16); color:#9ec7ff; font-size:10px; white-space:nowrap; text-overflow:ellipsis; }
    .kk-skill-card__name-input { width:100%; min-width:0; min-height:22px; padding:2px 4px; font-size:12px; }
    .kk-skill-card__actions { position:absolute; z-index:3; left:4px; bottom:4px; display:flex; gap:4px; margin:0; padding:3px; border:1px solid var(--border-color); border-radius:6px; background:rgba(25,25,25,.94); opacity:0; visibility:hidden; pointer-events:none; transition:opacity .12s ease; }
    .kk-skill-card:hover .kk-skill-card__actions,.kk-skill-card:focus-within .kk-skill-card__actions { opacity:1; visibility:visible; pointer-events:auto; }
    .kk-skill-card__actions button { min-height:20px; padding:1px 3px; font-size:10px; }
    .kk-skills-selector__dialog { position:fixed; z-index:10000; inset:0; display:flex; align-items:flex-start; justify-content:center; padding-top:20vh; background:rgba(0,0,0,.45); }
    .kk-skills-selector__dialog form { width:min(520px,calc(100vw - 32px)); padding:18px; border:1px solid rgba(150,170,200,.35); border-radius:10px; background:var(--comfy-menu-bg); box-shadow:0 12px 36px rgba(0,0,0,.45); }
    .kk-skills-selector__dialog label { display:block; margin-bottom:12px; color:var(--fg-color); font-size:13px; font-weight:600; }
    .kk-skills-selector__dialog input,.kk-skills-selector__dialog select { width:100%; min-height:34px; margin:0; padding:5px 9px; border:1px solid var(--border-color); border-radius:7px; background:var(--comfy-input-bg); color:var(--input-text); font-size:13px; }
    .kk-skills-selector__dialog select { appearance:auto; }
    .kk-skills-selector__tag-fields { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:14px; }
    .kk-skills-selector__dialog-actions { display:flex; justify-content:flex-end; gap:7px; }
    .kk-skills-selector__dialog-actions button { min-width:58px; min-height:28px; padding:4px 10px; border:1px solid var(--border-color); border-radius:6px; background:var(--comfy-input-bg); color:var(--input-text); cursor:pointer; }
    .kk-skills-selector__dialog-actions button[type="submit"] { border-color:#6aa9ff; background:rgba(106,169,255,.2); }
    .kk-skills-selector .kk-skill-card__delete { position:absolute; z-index:2; top:4px; right:4px; width:24px; min-height:24px; padding:0; border:1px solid #ff5f5f; border-radius:50%; background:rgba(70,0,0,.82); color:#ff5f5f; font-size:13px; line-height:22px; opacity:0; visibility:hidden; pointer-events:none; transition:opacity .12s ease; }
    .kk-skill-card:hover .kk-skill-card__delete,.kk-skill-card:focus-within .kk-skill-card__delete { opacity:1; visibility:visible; pointer-events:auto; }
    .kk-skills-selector__empty { display:flex; align-items:center; justify-content:center; min-height:160px; padding:12px; border:1px dashed var(--border-color); border-radius:7px; color:var(--descrip-text); text-align:center; }
  `;
  document.head.appendChild(style);
}

async function request(url, options) {
  const response = await api.fetchApi(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.ok === false) throw new Error(data.error || `请求失败：${response.status}`);
  return data;
}

function setup(node) {
  if (node.__kkSkillsSelector || node.comfyClass !== NODE_CLASS || typeof node.addDOMWidget !== "function") return;
  const idWidget = node.widgets?.find((widget) => widget.name === "Skill ID");
  if (!idWidget) return;
  idWidget.type = "hidden";
  idWidget.hidden = true;
  idWidget.computeSize = () => [0, 0];
  idWidget.draw = () => {};

  addStyles();
  node.__kkSkillsSelector = true;
  const state = { skills: [], selectedId: String(idWidget.value || ""), query: "", selectedTag: "", loading: false, message: "" };
  const root = document.createElement("div");
  root.className = "kk-skills-selector";
  root.onmousedown = (event) => event.stopPropagation();
  root.onwheel = (event) => event.stopPropagation();
  const bar = document.createElement("div");
  bar.className = "kk-skills-selector__bar";
  const search = document.createElement("input");
  search.placeholder = "搜索 Skill 名称或内容";
  const refreshButton = document.createElement("button");
  refreshButton.textContent = "刷新";
  const importButton = document.createElement("button");
  importButton.textContent = "导入模板包";
  const exportButton = document.createElement("button");
  exportButton.textContent = "导出模板包";
  const fileInput = document.createElement("input");
  fileInput.type = "file";
  fileInput.accept = ".zip,application/zip";
  fileInput.hidden = true;
  bar.append(search, refreshButton, importButton, exportButton, fileInput);
  const status = document.createElement("div");
  status.className = "kk-skills-selector__status";
  const tabs = document.createElement("div");
  tabs.className = "kk-skills-selector__tabs";
  tabs.setAttribute("role", "tablist");
  tabs.setAttribute("aria-label", "Skill 分类");
  const content = document.createElement("div");
  content.className = "kk-skills-selector__content";
  content.setAttribute("role", "tabpanel");
  root.append(bar, status, tabs, content);

  function select(id) {
    state.selectedId = id;
    idWidget.value = id;
    idWidget.callback?.(id);
    node.setDirtyCanvas?.(true, true);
    render();
  }

  function editDialog(title, value, callback) {
    const overlay = document.createElement("div");
    overlay.className = "kk-skills-selector__dialog";
    const form = document.createElement("form");
    const label = document.createElement("label");
    label.textContent = title;
    const input = document.createElement("input");
    input.value = value || "";
    const actions = document.createElement("div");
    actions.className = "kk-skills-selector__dialog-actions";
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.textContent = "取消";
    const save = document.createElement("button");
    save.type = "submit";
    save.textContent = "保存";
    actions.append(cancel, save);
    form.append(label, input, actions);
    overlay.appendChild(form);
    document.body.appendChild(overlay);
    const close = () => overlay.remove();
    cancel.onclick = close;
    overlay.onclick = (event) => { if (event.target === overlay) close(); };
    form.onsubmit = (event) => { event.preventDefault(); const next = input.value.trim(); close(); callback(next); };
    input.focus();
    input.select();
  }

  function rename(item) {
    editDialog("请输入新的 Skill 名称", item.name || item.id, (value) => {
      if (value && value !== item.name) saveSkillField(item, { name: value }, "名称已更新");
    });
  }

  async function saveSkillField(item, body, message) {
    state.message = "正在保存...";
    render();
    try {
      await request(`/kktools/skills/${encodeURIComponent(item.id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      state.message = message;
      await refresh();
    } catch (error) { state.message = error.message; render(); }
  }

  function editTag(item) {
    const overlay = document.createElement("div");
    overlay.className = "kk-skills-selector__dialog";
    const form = document.createElement("form");
    const label = document.createElement("label");
    label.textContent = "选择已有 Tag，或输入新的 Tag";
    const select = document.createElement("select");
    select.className = "kk-skills-selector__tag-select";
    const blank = document.createElement("option");
    blank.value = "";
    blank.textContent = "不使用 Tag";
    select.appendChild(blank);
    [...new Set([
      ...SKILL_TABS.slice(1).map((tab) => tab.id),
      ...state.skills.map((skill) => String(skill.tag || "").trim()).filter(Boolean),
    ])]
      .sort((a, b) => a.localeCompare(b, "zh-CN"))
      .forEach((tag) => { const option = document.createElement("option"); option.value = tag; option.textContent = tag; select.appendChild(option); });
    const input = document.createElement("input");
    input.value = item.tag || "";
    input.placeholder = "输入新 Tag";
    const fields = document.createElement("div");
    fields.className = "kk-skills-selector__tag-fields";
    fields.append(select, input);
    select.value = item.tag || "";
    select.onchange = () => { input.value = select.value; };
    const actions = document.createElement("div");
    actions.className = "kk-skills-selector__dialog-actions";
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.textContent = "取消";
    const save = document.createElement("button");
    save.type = "submit";
    save.textContent = "保存";
    actions.append(cancel, save);
    form.append(label, fields, actions);
    overlay.appendChild(form);
    document.body.appendChild(overlay);
    const close = () => overlay.remove();
    cancel.onclick = close;
    overlay.onclick = (event) => { if (event.target === overlay) close(); };
    form.onsubmit = (event) => {
      event.preventDefault();
      const value = input.value.trim();
      close();
      if (value !== String(item.tag || "").trim()) saveSkillField(item, { tag: value }, value ? "Tag 已更新" : "Tag 已清空");
    };
    input.focus();
    input.select();
  }

  async function remove(item) {
    if (!window.confirm(`确定删除 Skill“${item.name || item.id}”吗？`)) return;
    try {
      await request(`/kktools/skills/${encodeURIComponent(item.id)}`, { method: "DELETE" });
      if (state.selectedId === item.id) select("");
      await refresh();
    } catch (error) { state.message = error.message; render(); }
  }

  function card(item) {
    const element = document.createElement("div");
    element.className = `kk-skill-card${item.id === state.selectedId ? " selected" : ""}`;
    element.onclick = () => select(item.id);
    const cover = document.createElement("div");
    cover.className = "kk-skill-card__cover";
    if (item.coverUrl) {
      const image = document.createElement("img");
      image.loading = "lazy";
      image.src = item.coverUrl;
      image.onerror = () => { cover.textContent = "无封面"; };
      cover.appendChild(image);
    } else cover.textContent = "Skill";
    const body = document.createElement("div");
    body.className = "kk-skill-card__body";
    const name = document.createElement("div");
    name.className = "kk-skill-card__name";
    name.textContent = item.name || item.id;
    const tag = document.createElement("div");
    tag.className = "kk-skill-card__tag";
    tag.textContent = item.tag || "";
    tag.hidden = !item.tag;
    const actions = document.createElement("div");
    actions.className = "kk-skill-card__actions";
    const renameButton = document.createElement("button");
    renameButton.textContent = "改名";
    renameButton.onpointerdown = (event) => event.stopPropagation();
    renameButton.onclick = (event) => { event.preventDefault(); event.stopPropagation(); rename(item); };
    const tagButton = document.createElement("button");
    tagButton.textContent = "改Tag";
    tagButton.onpointerdown = (event) => event.stopPropagation();
    tagButton.onclick = (event) => { event.preventDefault(); event.stopPropagation(); editTag(item); };
    const deleteButton = document.createElement("button");
    deleteButton.className = "kk-skill-card__delete";
    deleteButton.title = "删除 Skill";
    deleteButton.textContent = "❌";
    deleteButton.onclick = (event) => { event.stopPropagation(); remove(item); };
    actions.append(renameButton, tagButton);
    const tagRow = document.createElement("div");
    tagRow.className = "kk-skill-card__tag-row";
    tagRow.append(tag);
    body.append(name, tagRow, actions);
    element.append(cover, body, deleteButton);
    return element;
  }

  function render() {
    const query = state.query.toLowerCase();
    const items = state.skills.filter((item) => {
      const matchesTag = !state.selectedTag || skillTab(item) === state.selectedTag;
      const matchesQuery = [item.name, item.tag, item.description, item.sourceFilename].join(" ").toLowerCase().includes(query);
      return matchesTag && matchesQuery;
    });
    status.textContent = state.loading ? "正在读取 Skills 模板库..." : state.message || "";
    const tagCounts = new Map(SKILL_TABS.slice(1).map((tab) => [tab.id, 0]));
    state.skills.forEach((item) => {
      const tag = skillTab(item);
      tagCounts.set(tag, (tagCounts.get(tag) || 0) + 1);
    });
    tabs.innerHTML = "";
    SKILL_TABS.forEach((tab, index) => {
      const button = document.createElement("button");
      const count = tab.id ? tagCounts.get(tab.id) || 0 : state.skills.length;
      button.type = "button";
      button.textContent = `${tab.label} ${count}`;
      button.dataset.tab = tab.id;
      button.className = state.selectedTag === tab.id ? "selected" : "";
      button.setAttribute("role", "tab");
      button.setAttribute("aria-selected", String(state.selectedTag === tab.id));
      button.tabIndex = state.selectedTag === tab.id ? 0 : -1;
      button.onclick = (event) => { event.stopPropagation(); state.selectedTag = tab.id; render(); };
      button.onkeydown = (event) => {
        if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
        event.preventDefault();
        const offset = event.key === 'ArrowRight' ? 1 : -1;
        const next = (index + offset + SKILL_TABS.length) % SKILL_TABS.length;
        state.selectedTag = SKILL_TABS[next].id;
        render();
        requestAnimationFrame(() => tabs.querySelector(`[data-tab="${CSS.escape(state.selectedTag)}"]`)?.focus());
      };
      tabs.appendChild(button);
    });
    content.innerHTML = "";
    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "kk-skills-selector__empty";
      empty.textContent = state.skills.length ? "当前分类暂无 Skill。" : "暂无 Skill。连接 kkMarkdown上传 后执行此节点即可入库。";
      content.appendChild(empty);
      return;
    }
    const grid = document.createElement("div");
    grid.className = "kk-skills-selector__grid";
    items.forEach((item) => grid.appendChild(card(item)));
    content.appendChild(grid);
  }

  async function refresh() {
    state.loading = true;
    state.message = "";
    render();
    try {
      const data = await request(`/kktools/skills?t=${Date.now()}`);
      state.skills = Array.isArray(data.skills) ? data.skills : [];
    } catch (error) { state.message = error.message; }
    state.loading = false;
    render();
  }

  search.oninput = () => { state.query = search.value; render(); };
  refreshButton.onclick = refresh;
  importButton.onclick = () => fileInput.click();
  fileInput.onchange = async () => {
    const file = fileInput.files?.[0];
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    state.message = "正在导入模板包...";
    render();
    try {
      const data = await request("/kktools/skills/import", { method: "POST", body: form });
      state.message = `已导入 ${data.imported || 0} 个模板`;
      await refresh();
    } catch (error) { state.message = error.message; render(); }
    fileInput.value = "";
  };
  exportButton.onclick = () => {
    const link = document.createElement("a");
    link.href = "/kktools/skills/export?t=" + Date.now();
    link.download = "kktools-skills-package.zip";
    link.click();
  };
  node.addDOMWidget("Skills模板选择器", "kk-skills-selector", root, { serialize: false, hideOnZoom: false });
  const originalExecuted = node.onExecuted;
  node.onExecuted = function (message, ...args) {
    const result = originalExecuted?.call(this, message, ...args);
    const executedId = Array.isArray(message?.skill_id) ? message.skill_id[0] : message?.skill_id;
    if (executedId) {
      state.selectedId = String(executedId);
      idWidget.value = state.selectedId;
      idWidget.callback?.(state.selectedId);
    }
    refresh();
    return result;
  };
  if ((node.size?.[0] || 0) < 420 || (node.size?.[1] || 0) < 430) {
    node.setSize?.([Math.max(node.size?.[0] || 0, 420), Math.max(node.size?.[1] || 0, 430)]);
  }
  refresh();
}

app.registerExtension({
  name: "kktools.SkillsTemplateSelector",
  nodeCreated(node) { setup(node); requestAnimationFrame(() => setup(node)); },
  loadedGraphNode(node) { setup(node); requestAnimationFrame(() => setup(node)); },
});
