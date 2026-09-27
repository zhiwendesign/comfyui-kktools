import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const NODE_CLASS = "kkimage Comparer";
const STYLE_ID = "kktools-image-comparer-style";

function addStyles() {
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .kk-image-comparer { box-sizing:border-box; display:flex; flex-direction:column; gap:7px; width:100%; height:100%; min-height:300px; padding:4px; color:var(--fg-color); }
    .kk-image-comparer__toolbar { display:flex; gap:6px; align-items:center; }
    .kk-image-comparer__select { min-width:0; flex:1; height:26px; padding:0 7px; border:1px solid var(--border-color); border-radius:5px; background:var(--comfy-input-bg); color:var(--input-text); }
    .kk-image-comparer__stage { position:relative; flex:1; min-height:250px; overflow:hidden; border:1px solid var(--border-color); border-radius:7px; background:#111; cursor:ew-resize; user-select:none; touch-action:none; }
    .kk-image-comparer__layer { position:absolute; inset:0; width:100%; height:100%; object-fit:contain; pointer-events:none; }
    .kk-image-comparer__layer--b { clip-path:inset(0 50% 0 0); }
    .kk-image-comparer__divider { position:absolute; top:0; bottom:0; left:50%; width:2px; transform:translateX(-1px); background:rgba(255,255,255,.9); box-shadow:0 0 5px rgba(0,0,0,.8); pointer-events:none; }
    .kk-image-comparer__label { position:absolute; top:9px; padding:3px 7px; border-radius:4px; background:rgba(0,0,0,.65); color:#fff; font:600 11px/1.2 sans-serif; pointer-events:none; }
    .kk-image-comparer__label--a { left:9px; } .kk-image-comparer__label--b { right:9px; }
    .kk-image-comparer__empty { position:absolute; inset:0; display:grid; place-items:center; color:#999; font-size:12px; pointer-events:none; }
  `;
  document.head.append(style);
}

function imageUrl(image) {
  const params = new URLSearchParams({ filename: image.filename, type: image.type || "temp", rand: String(Date.now()) });
  if (image.subfolder) params.set("subfolder", image.subfolder);
  return api.apiURL(`/view?${params.toString()}`);
}

function setup(node) {
  if (node.__kkImageComparer || node.comfyClass !== NODE_CLASS || typeof node.addDOMWidget !== "function") return;
  addStyles();
  const root = document.createElement("div");
  root.className = "kk-image-comparer";
  const toolbar = document.createElement("div");
  toolbar.className = "kk-image-comparer__toolbar";
  const selectA = document.createElement("select");
  const selectB = document.createElement("select");
  selectA.className = selectB.className = "kk-image-comparer__select";
  toolbar.append(selectA, selectB);
  const stage = document.createElement("div");
  stage.className = "kk-image-comparer__stage";
  const imageA = document.createElement("img");
  const imageB = document.createElement("img");
  imageA.className = "kk-image-comparer__layer";
  imageB.className = "kk-image-comparer__layer kk-image-comparer__layer--b";
  imageA.draggable = imageB.draggable = false;
  const divider = document.createElement("div");
  divider.className = "kk-image-comparer__divider";
  const labelA = document.createElement("span");
  const labelB = document.createElement("span");
  labelA.className = "kk-image-comparer__label kk-image-comparer__label--a";
  labelB.className = "kk-image-comparer__label kk-image-comparer__label--b";
  labelA.textContent = "A";
  labelB.textContent = "B";
  const empty = document.createElement("div");
  empty.className = "kk-image-comparer__empty";
  empty.textContent = "连接图像后运行工作流";
  stage.append(imageA, imageB, divider, labelA, labelB, empty);
  root.append(toolbar, stage);

  const state = { images: [], a: 0, b: 1, position: 50 };
  const modeWidget = node.addWidget("combo", "对比方式", "滑动", () => render(), { values: ["滑动", "点击"] });

  function fillSelect(select, selected) {
    select.replaceChildren();
    state.images.forEach((item, index) => {
      const option = document.createElement("option");
      option.value = String(index);
      option.textContent = item.label;
      option.selected = index === selected;
      select.append(option);
    });
  }

  function render() {
    const a = state.images[state.a];
    const b = state.images[state.b];
    const hasPair = Boolean(a && b && state.a !== state.b);
    const aUrl = a?.url || "";
    const bUrl = b?.url || "";
    if (imageA.dataset.src !== aUrl) { imageA.src = aUrl; imageA.dataset.src = aUrl; }
    if (imageB.dataset.src !== bUrl) { imageB.src = bUrl; imageB.dataset.src = bUrl; }
    imageA.style.display = a ? "block" : "none";
    imageB.style.display = hasPair ? "block" : "none";
    divider.style.display = hasPair && modeWidget.value === "滑动" ? "block" : "none";
    labelA.style.display = a ? "block" : "none";
    labelB.style.display = hasPair ? "block" : "none";
    empty.style.display = a ? "none" : "grid";
    toolbar.style.display = state.images.length > 1 ? "flex" : "none";
    stage.style.cursor = hasPair ? (modeWidget.value === "滑动" ? "ew-resize" : "pointer") : "default";
    imageB.style.clipPath = modeWidget.value === "滑动" ? `inset(0 ${100 - state.position}% 0 0)` : "none";
    imageB.style.opacity = modeWidget.value === "点击" ? "0" : "1";
    divider.style.left = `${state.position}%`;
  }

  function setPosition(event) {
    const bounds = stage.getBoundingClientRect();
    state.position = Math.max(0, Math.min(100, ((event.clientX - bounds.left) / bounds.width) * 100));
    render();
  }
  stage.addEventListener("pointermove", (event) => { if (modeWidget.value === "滑动" && state.images.length > 1) setPosition(event); });
  stage.addEventListener("pointerdown", (event) => {
    event.stopPropagation();
    if (modeWidget.value === "点击" && state.images.length > 1) imageB.style.opacity = "1";
    else setPosition(event);
  });
  const release = () => { if (modeWidget.value === "点击") imageB.style.opacity = "0"; };
  stage.addEventListener("pointerup", release);
  stage.addEventListener("pointerleave", release);
  root.addEventListener("wheel", (event) => event.stopPropagation());
  selectA.onchange = () => { state.a = Number(selectA.value); render(); };
  selectB.onchange = () => { state.b = Number(selectB.value); render(); };

  node.__kkImageComparer = { state, render };
  node.addDOMWidget("图像对比", "kk-image-comparer", root, { serialize:false, hideOnZoom:false, getMinHeight:() => 320 });
  const originalExecuted = node.onExecuted;
  node.onExecuted = function (message, ...args) {
    const result = originalExecuted?.call(this, message, ...args);
    const aImages = Array.isArray(message?.a_images) ? message.a_images : [];
    const bImages = Array.isArray(message?.b_images) ? message.b_images : [];
    state.images = [
      ...aImages.map((item, index) => ({ label:`A${index + 1}`, url:imageUrl(item) })),
      ...bImages.map((item, index) => ({ label:`B${index + 1}`, url:imageUrl(item) })),
    ];
    state.a = 0;
    state.b = bImages.length ? aImages.length : (aImages.length > 1 ? 1 : 0);
    fillSelect(selectA, state.a);
    fillSelect(selectB, state.b);
    render();
    return result;
  };
  if ((node.size?.[0] || 0) < 400 || (node.size?.[1] || 0) < 430) node.setSize?.([Math.max(node.size?.[0] || 0, 400), Math.max(node.size?.[1] || 0, 430)]);
  render();
}

app.registerExtension({
  name: "kktools.ImageComparer",
  nodeCreated(node) { setup(node); requestAnimationFrame(() => setup(node)); },
  loadedGraphNode(node) { setup(node); requestAnimationFrame(() => setup(node)); },
});
