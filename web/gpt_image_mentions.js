import { app } from "../../scripts/app.js";

const NODE_CLASS = "kkGPT-image_API";
const STYLE_ID = "kktools-gpt-image-mentions-style";
const IMAGE_INPUT_RE = /^image(?:_\d+)?$/;
const STRING_INPUT_RE = /^string(?:_\d+)?$/;

function addStyles() {
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .kk-image-mentions { position:relative; box-sizing:border-box; display:flex; flex-direction:column; gap:7px; width:100%; min-height:150px; padding:2px 4px 4px; color:var(--fg-color); font:12px/1.45 sans-serif; }
    .kk-image-mentions__refs { display:flex; flex-wrap:wrap; gap:5px; min-height:0; }
    .kk-image-mentions__refs:empty { display:none; }
    .kk-image-mentions__chip { max-width:100%; overflow:hidden; padding:3px 7px; border:1px solid color-mix(in srgb, #a855f7 65%, var(--border-color)); border-radius:7px; background:color-mix(in srgb, #a855f7 16%, var(--comfy-input-bg, #111)); color:var(--fg-color); text-overflow:ellipsis; white-space:nowrap; cursor:pointer; }
    .kk-image-mentions__chip:hover { background:color-mix(in srgb, #a855f7 28%, var(--comfy-input-bg, #111)); }
    .kk-image-mentions__editor { box-sizing:border-box; flex:1; min-height:112px; overflow:auto; padding:9px; border:1px solid var(--border-color); border-radius:7px; outline:none; background:var(--comfy-input-bg, #111); color:var(--input-text, var(--fg-color)); white-space:pre-wrap; word-break:break-word; cursor:text; }
    .kk-image-mentions__editor:focus { border-color:#6aa9ff; box-shadow:0 0 0 1px #6aa9ff; }
    .kk-image-mentions__editor:empty::before { color:var(--descrip-text); content:attr(data-placeholder); pointer-events:none; }
    .kk-image-mentions__mention { display:inline-block; margin:1px 2px; padding:2px 6px; border-radius:6px; background:rgba(35, 181, 78, .2); color:#55df72; white-space:nowrap; user-select:all; }
    .kk-image-mentions__menu { position:absolute; z-index:1000; right:4px; bottom:6px; left:4px; display:none; max-height:160px; overflow:auto; padding:4px; border:1px solid var(--border-color); border-radius:7px; background:var(--comfy-menu-bg, #202020); box-shadow:0 8px 24px rgba(0,0,0,.45); }
    .kk-image-mentions__menu.open { display:block; }
    .kk-image-mentions__option { display:block; width:100%; overflow:hidden; padding:6px 8px; border:0; border-radius:5px; background:transparent; color:var(--fg-color); text-align:left; text-overflow:ellipsis; white-space:nowrap; cursor:pointer; }
    .kk-image-mentions__option.selected, .kk-image-mentions__option:hover { background:rgba(106,169,255,.2); }
    .kk-image-mentions__empty { padding:7px 8px; color:var(--descrip-text); }
  `;
  document.head.appendChild(style);
}

function graphLink(graph, linkId) {
  if (linkId == null || !graph) return null;
  if (typeof graph.getLink === "function") {
    const link = graph.getLink(linkId);
    if (link) return link;
  }
  if (typeof graph.links?.get === "function") return graph.links.get(linkId) || null;
  if (Array.isArray(graph.links)) {
    return graph.links[linkId] || graph.links.find((link) => link?.id === linkId) || null;
  }
  return graph.links?.[linkId] || null;
}

function nodeIdLabel(id) {
  const value = String(id ?? "?");
  return /^\d+$/.test(value) ? value.padStart(2, "0") : value.slice(0, 8);
}

function connectedReferences(node) {
  const graph = node.graph || app.graph;
  const references = [];
  let imageIndex = 0;
  for (let slot = 0; slot < (node.inputs || []).length; slot += 1) {
    const input = node.inputs[slot];
    const isImage = IMAGE_INPUT_RE.test(input?.name || "");
    if (!isImage && !STRING_INPUT_RE.test(input?.name || "")) continue;
    const link = node.getInputLink?.(slot) || graphLink(graph, input.link);
    if (!link) continue;
    const originId = link.origin_id ?? link.originId;
    const originSlot = link.origin_slot ?? link.originSlot;
    const origin = graph?.getNodeById?.(originId);
    const output = origin?.outputs?.[originSlot];
    const title = String(origin?.title || origin?.comfyClass || origin?.type || input.name).trim();
    if (isImage) imageIndex += 1;
    references.push({
      token: isImage ? `@Image${imageIndex}` : `@${input.name}`,
      inputName: input.name,
      sourceLabel: `#${nodeIdLabel(originId)} ${title} ${output?.type || (isImage ? "IMAGE" : "STRING")}`,
    });
  }
  return references;
}

function readEditorNode(node, root) {
  if (node.nodeType === Node.TEXT_NODE) return node.data;
  if (node.nodeType !== Node.ELEMENT_NODE) return "";
  if (node.dataset?.imageMention) return node.dataset.imageMention;
  if (node.tagName === "BR") return "\n";

  let value = "";
  for (const child of node.childNodes) value += readEditorNode(child, root);
  if (node !== root && /^(DIV|P)$/.test(node.tagName) && node.nextSibling && !value.endsWith("\n")) value += "\n";
  return value;
}

function editorValue(editor) {
  return readEditorNode(editor, editor).replace(/\u00a0/g, " ");
}

function mentionElement(reference) {
  const mention = document.createElement("span");
  mention.className = "kk-image-mentions__mention";
  mention.contentEditable = "false";
  mention.dataset.imageMention = reference.token;
  mention.title = `${reference.inputName} · ${reference.sourceLabel}`;
  mention.textContent = `▣ ${reference.inputName}`;
  return mention;
}

function renderEditorValue(editor, value, references) {
  const byToken = new Map(references.map((reference) => [reference.token.toLocaleLowerCase(), reference]));
  const firstImage = references.find((reference) => reference.token.toLocaleLowerCase() === "@image1");
  if (firstImage) byToken.set("@image", firstImage);
  const fragment = document.createDocumentFragment();
  const text = String(value || "");
  const pattern = /@(?:image\d*|string(?:_\d+)?)(?!\w)/ig;
  let position = 0;
  let previousEnd = -1;
  for (const match of text.matchAll(pattern)) {
    const start = match.index;
    if (start > 0 && start !== previousEnd && /[\p{L}\p{N}_]/u.test(text[start - 1])) continue;
    const reference = byToken.get(match[0].toLocaleLowerCase());
    if (!reference) continue;
    fragment.append(document.createTextNode(text.slice(position, start)));
    fragment.append(mentionElement(reference));
    position = start + match[0].length;
    previousEnd = position;
  }
  fragment.append(document.createTextNode(text.slice(position)));
  editor.replaceChildren(fragment);
}

function mentionQuery(editor) {
  const selection = window.getSelection();
  if (!selection?.isCollapsed || !editor.contains(selection.anchorNode)) return null;
  const node = selection.anchorNode;
  if (node?.nodeType !== Node.TEXT_NODE) return null;
  const before = node.data.slice(0, selection.anchorOffset);
  const match = before.match(/(?:^|[\s([{])@([^\s@]*)$/u);
  if (!match) return null;
  return {
    node,
    start: selection.anchorOffset - match[1].length - 1,
    end: selection.anchorOffset,
    query: match[1].toLocaleLowerCase(),
  };
}

function setup(node) {
  if ((node.comfyClass || node.type) !== NODE_CLASS || typeof node.addDOMWidget !== "function") return;
  if (node.__kkImageMentionEditor) {
    node.__kkImageMentionEditor.refresh();
    return;
  }

  const promptWidget = node.widgets?.find((widget) => widget.name === "prompt");
  if (!promptWidget) return;

  addStyles();
  promptWidget.type = "hidden";
  promptWidget.hidden = true;
  promptWidget.options = { ...(promptWidget.options || {}), hidden: true };
  promptWidget.computeSize = () => [0, -4];
  promptWidget.draw = () => {};

  const root = document.createElement("div");
  root.className = "kk-image-mentions";
  const chips = document.createElement("div");
  chips.className = "kk-image-mentions__refs";
  const editor = document.createElement("div");
  editor.className = "kk-image-mentions__editor";
  editor.contentEditable = "true";
  editor.spellcheck = true;
  editor.dataset.placeholder = "输入提示词；输入 @ 可引用已连接的图像或字符串";
  editor.setAttribute("role", "textbox");
  editor.setAttribute("aria-label", "prompt");
  editor.setAttribute("aria-multiline", "true");
  const menu = document.createElement("div");
  menu.className = "kk-image-mentions__menu";
  root.append(chips, editor, menu);

  const state = {
    references: [],
    options: [],
    selected: 0,
    syncing: false,
    mentionRange: null,
  };

  function syncWidget() {
    const value = editorValue(editor);
    if (String(promptWidget.value || "") === value) return;
    state.syncing = true;
    promptWidget.value = value;
    promptWidget.callback?.(value);
    state.syncing = false;
    node.graph?.setDirtyCanvas?.(true, true);
  }

  function closeMenu() {
    state.options = [];
    state.selected = 0;
    state.mentionRange = null;
    menu.classList.remove("open");
    menu.replaceChildren();
  }

  function insertReference(reference) {
    const selection = window.getSelection();
    const query = mentionQuery(editor);
    const range = state.mentionRange?.cloneRange() || document.createRange();
    if (query) {
      range.setStart(query.node, query.start);
      range.setEnd(query.node, query.end);
    } else if (!state.mentionRange && selection?.rangeCount && editor.contains(selection.anchorNode)) {
      range.setStart(selection.anchorNode, selection.anchorOffset);
      range.collapse(true);
    } else if (!state.mentionRange) {
      range.selectNodeContents(editor);
      range.collapse(false);
    }
    editor.focus();
    range.deleteContents();
    const mention = mentionElement(reference);
    const space = document.createTextNode(" ");
    range.insertNode(space);
    range.insertNode(mention);
    range.setStartAfter(space);
    range.collapse(true);
    selection?.removeAllRanges();
    selection?.addRange(range);
    syncWidget();
    closeMenu();
  }

  function renderMenu() {
    const context = mentionQuery(editor);
    if (!context) {
      closeMenu();
      return;
    }
    state.mentionRange = document.createRange();
    state.mentionRange.setStart(context.node, context.start);
    state.mentionRange.setEnd(context.node, context.end);
    const query = context.query;
    state.options = state.references.filter((reference) =>
      `${reference.token} ${reference.inputName} ${reference.sourceLabel}`.toLocaleLowerCase().includes(query)
    );
    state.selected = Math.min(state.selected, Math.max(0, state.options.length - 1));
    menu.replaceChildren();
    if (!state.references.length) {
      const empty = document.createElement("div");
      empty.className = "kk-image-mentions__empty";
      empty.textContent = "请先连接图像或字符串输入";
      menu.appendChild(empty);
    } else if (!state.options.length) {
      const empty = document.createElement("div");
      empty.className = "kk-image-mentions__empty";
      empty.textContent = "没有匹配的图像或字符串";
      menu.appendChild(empty);
    } else {
      state.options.forEach((reference, index) => {
        const option = document.createElement("button");
        option.type = "button";
        option.className = `kk-image-mentions__option${index === state.selected ? " selected" : ""}`;
        option.textContent = `@${reference.inputName}  ${reference.sourceLabel}`;
        option.onpointerdown = (event) => {
          event.preventDefault();
          event.stopPropagation();
        };
        option.onclick = (event) => {
          event.preventDefault();
          event.stopPropagation();
          insertReference(reference);
        };
        menu.appendChild(option);
      });
    }
    menu.classList.add("open");
  }

  function renderChips() {
    chips.replaceChildren();
    for (const reference of state.references) {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "kk-image-mentions__chip";
      chip.title = `${reference.sourceLabel}；点击插入 @${reference.inputName}`;
      chip.textContent = `▣ ${reference.inputName}`;
      chip.onclick = (event) => {
        event.preventDefault();
        event.stopPropagation();
        insertReference(reference);
      };
      chips.appendChild(chip);
    }
  }

  function refresh() {
    const value = editorValue(editor) || String(promptWidget.value || "");
    state.references = connectedReferences(node);
    renderChips();
    if (document.activeElement !== editor) renderEditorValue(editor, value, state.references);
    if (menu.classList.contains("open")) renderMenu();
  }

  const originalCallback = promptWidget.callback;
  promptWidget.callback = function (value) {
    const result = originalCallback?.apply(this, arguments);
    if (!state.syncing && document.activeElement !== editor) {
      renderEditorValue(editor, value, state.references);
    }
    return result;
  };

  editor.addEventListener("input", () => {
    syncWidget();
    renderMenu();
  });
  editor.addEventListener("keydown", (event) => {
    if (!menu.classList.contains("open")) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const direction = event.key === "ArrowDown" ? 1 : -1;
      const count = state.options.length;
      if (count) state.selected = (state.selected + direction + count) % count;
      renderMenu();
    } else if ((event.key === "Enter" || event.key === "Tab") && state.options.length) {
      event.preventDefault();
      insertReference(state.options[state.selected]);
    } else if (event.key === "Escape") {
      event.preventDefault();
      closeMenu();
    }
  });
  editor.addEventListener("paste", (event) => {
    event.preventDefault();
    document.execCommand("insertText", false, event.clipboardData?.getData("text/plain") || "");
  });
  editor.addEventListener("blur", () => window.setTimeout(closeMenu, 120));
  root.addEventListener("mousedown", (event) => event.stopPropagation());
  root.addEventListener("wheel", (event) => event.stopPropagation());

  const originalConnectionsChange = node.onConnectionsChange;
  node.onConnectionsChange = function () {
    const result = originalConnectionsChange?.apply(this, arguments);
    requestAnimationFrame(refresh);
    return result;
  };

  node.__kkImageMentionEditor = { refresh };
  node.addDOMWidget("prompt", "kk-image-mentions", root, {
    serialize: false,
    hideOnZoom: false,
    getMinHeight: () => 150,
    getMaxHeight: () => 280,
  });
  state.references = connectedReferences(node);
  renderChips();
  renderEditorValue(editor, promptWidget.value, state.references);
  requestAnimationFrame(refresh);
  window.setTimeout(refresh, 100);

  const width = Math.max(360, Number(node.size?.[0]) || 0);
  const height = Math.max(Number(node.size?.[1]) || 0, Number(node.computeSize?.()?.[1]) || 0);
  node.setSize?.([width, height]);
}

function setupSoon(node) {
  setup(node);
  requestAnimationFrame(() => setup(node));
}

app.registerExtension({
  name: "kktools.GPTImageMentions",
  nodeCreated(node) {
    setupSoon(node);
  },
  loadedGraphNode(node) {
    setupSoon(node);
  },
});
