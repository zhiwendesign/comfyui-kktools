import { app } from "/scripts/app.js";
import { api } from "/scripts/api.js";

const NODE_CLASS = "kkSkills模板选择器";

function addStyles() {
  if (document.getElementById("kk-skills-selector-style")) return;
  const style = document.createElement("style");
  style.id = "kk-skills-selector-style";
  style.textContent = `
    .kk-skills-selector { display:flex; flex-direction:column; gap:8px; width:100%; height:300px; padding:8px; box-sizing:border-box; color:var(--fg-color); }
    .kk-skills-selector * { box-sizing:border-box; }
    .kk-skills-selector__bar { display:grid; grid-template-columns:minmax(100px,1fr) auto; gap:6px; }
    .kk-skills-selector input,.kk-skills-selector button { min-height:26px; border:1px solid var(--border-color); border-radius:6px; background:var(--comfy-input-bg); color:var(--input-text); }
    .kk-skills-selector input { width:100%; padding:4px 8px; }
    .kk-skills-selector button { padding:3px 7px; cursor:pointer; }
    .kk-skills-selector__status { min-height:16px; color:var(--descrip-text); font-size:11px; }
    .kk-skills-selector__content { flex:1; min-height:180px; overflow-y:auto; }
    .kk-skills-selector__grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(100px,1fr)); gap:8px; }
    .kk-skill-card { position:relative; overflow:hidden; border:1px solid var(--border-color); border-radius:7px; background:var(--comfy-menu-bg); cursor:pointer; }
    .kk-skill-card.selected { border-color:#6aa9ff; box-shadow:0 0 0 1px #6aa9ff inset; }
    .kk-skill-card__cover { display:flex; align-items:center; justify-content:center; width:100%; aspect-ratio:16/10; overflow:hidden; background:var(--comfy-input-bg); color:var(--descrip-text); font-size:11px; }
    .kk-skill-card__cover img { width:100%; height:100%; object-fit:cover; }
    .kk-skill-card__body { position:relative; padding:6px; }
    .kk-skill-card__name { overflow:hidden; color:var(--fg-color); font-size:12px; font-weight:600; white-space:nowrap; text-overflow:ellipsis; }
    .kk-skill-card__name-input { width:100%; min-width:0; min-height:22px; padding:2px 4px; font-size:12px; }
    .kk-skill-card__actions { position:absolute; right:4px; top:3px; display:flex; gap:4px; margin:0; opacity:0; visibility:hidden; pointer-events:none; transition:opacity .12s ease; }
    .kk-skill-card:hover .kk-skill-card__actions,.kk-skill-card:focus-within .kk-skill-card__actions { opacity:1; visibility:visible; pointer-events:auto; }
    .kk-skill-card__actions button { flex:1; min-height:20px; padding:1px 3px; font-size:10px; }
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
  idWidget.computeSize = () => [0, -4];
  idWidget.draw = () => {};

  addStyles();
  node.__kkSkillsSelector = true;
  const state = { skills: [], selectedId: String(idWidget.value || ""), query: "", loading: false, message: "" };
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
  bar.append(search, refreshButton);
  const status = document.createElement("div");
  status.className = "kk-skills-selector__status";
  const content = document.createElement("div");
  content.className = "kk-skills-selector__content";
  root.append(bar, status, content);

  function select(id) {
    state.selectedId = id;
    idWidget.value = id;
    idWidget.callback?.(id);
    node.setDirtyCanvas?.(true, true);
    render();
  }

  function rename(item, nameElement) {
    const input = document.createElement("input");
    input.className = "kk-skill-card__name-input";
    input.value = item.name || item.id;
    input.onclick = (event) => event.stopPropagation();
    input.onmousedown = (event) => event.stopPropagation();
    nameElement.replaceWith(input);
    input.focus();
    input.select();

    let finished = false;
    async function finish(save) {
      if (finished) return;
      finished = true;
      const name = input.value.trim();
      if (!save || !name || name === item.name) {
        render();
        return;
      }
      state.message = "正在保存名称...";
      render();
      try {
        await request(`/kktools/skills/${encodeURIComponent(item.id)}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name }),
        });
        state.message = "已改名";
        await refresh();
      } catch (error) { state.message = error.message; render(); }
    }

    input.onkeydown = (event) => {
      event.stopPropagation();
      if (event.key === "Enter") finish(true);
      if (event.key === "Escape") finish(false);
    };
    input.onblur = () => finish(true);
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
    const actions = document.createElement("div");
    actions.className = "kk-skill-card__actions";
    const renameButton = document.createElement("button");
    renameButton.textContent = "改名";
    renameButton.onclick = (event) => { event.stopPropagation(); rename(item, name); };
    const deleteButton = document.createElement("button");
    deleteButton.className = "kk-skill-card__delete";
    deleteButton.title = "删除 Skill";
    deleteButton.textContent = "❌";
    deleteButton.onclick = (event) => { event.stopPropagation(); remove(item); };
    actions.append(renameButton);
    body.append(name, actions);
    element.append(cover, body, deleteButton);
    return element;
  }

  function render() {
    const query = state.query.toLowerCase();
    const items = state.skills.filter((item) => [item.name, item.description, item.sourceFilename].join(" ").toLowerCase().includes(query));
    status.textContent = state.loading ? "正在读取 Skills 模板库..." : state.message || `共 ${state.skills.length} 个，显示 ${items.length} 个`;
    content.innerHTML = "";
    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "kk-skills-selector__empty";
      empty.textContent = "暂无 Skill。连接 kkMarkdown上传 后执行此节点即可入库。";
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
  if ((node.size?.[0] || 0) < 420 || (node.size?.[1] || 0) < 430) node.setSize?.([Math.max(node.size?.[0] || 0, 420), Math.max(node.size?.[1] || 0, 430)]);
  refresh();
}

app.registerExtension({
  name: "kktools.SkillsTemplateSelector",
  nodeCreated(node) { setup(node); requestAnimationFrame(() => setup(node)); },
  loadedGraphNode(node) { setup(node); requestAnimationFrame(() => setup(node)); },
});
