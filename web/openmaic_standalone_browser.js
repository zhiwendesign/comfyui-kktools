import { app } from "/scripts/app.js";
import { api } from "/scripts/api.js";

const STANDALONE_NODE_TYPES = [
  "OpenMAICStandaloneImportCourseware",
  "OpenMAICStandaloneGenerateScript",
  "OpenMAICStandaloneBatchTTS",
  "OpenMAICStandaloneTTSAdapter",
  "OpenMAICStandaloneCollectTTSAudio",
  "OpenMAICStandaloneExportVideo",
];

const NODE_POLISH = {
  OpenMAICStandaloneImportCourseware: {
    step: "01",
    title: "1. 导入课件",
    defaultTitles: ["OpenMAIC 独立导入课件", "1. 导入课件"],
    detail: "PPTX / PDF / 图片目录 -> 页图与页面文本",
    color: "#1f6970",
    bgcolor: "#10292d",
    accent: "#66d9e8",
    size: [560, 320],
  },
  OpenMAICStandaloneGenerateScript: {
    step: "02",
    title: "2. 生成讲稿",
    defaultTitles: ["OpenMAIC 独立生成讲稿", "2. 生成讲稿"],
    detail: "VLM 看图 + 讲稿匹配 / 并发口语化改写",
    color: "#264d82",
    bgcolor: "#111f38",
    accent: "#82b1ff",
    size: [560, 455],
  },
  OpenMAICStandaloneBatchTTS: {
    step: "03",
    title: "3. 批量配音",
    defaultTitles: ["OpenMAIC 独立批量TTS", "3. 批量配音"],
    detail: "API / Gradio -> 音频清单与时间轴",
    color: "#2f644c",
    bgcolor: "#10271d",
    accent: "#8be9b2",
    size: [560, 400],
  },
  OpenMAICStandaloneTTSAdapter: {
    step: "03",
    title: "3. TTS文本转接器",
    defaultTitles: ["OpenMAIC TTS文本转接器", "3. TTS文本转接器"],
    detail: "分段讲稿 -> 可接 IndexTTS2.text 的批量文本",
    color: "#315f75",
    bgcolor: "#102734",
    accent: "#8bd3ff",
    size: [480, 220],
  },
  OpenMAICStandaloneCollectTTSAudio: {
    step: "05",
    title: "5. 收集TTS音频",
    defaultTitles: ["OpenMAIC 收集TTS音频", "5. 收集TTS音频"],
    detail: "IndexTTS2 AUDIO 列表 -> 音频清单与时间轴",
    color: "#2f644c",
    bgcolor: "#10271d",
    accent: "#8be9b2",
    size: [540, 300],
  },
  OpenMAICStandaloneExportVideo: {
    step: "06",
    title: "6. 导出视频",
    defaultTitles: ["OpenMAIC 独立导出课件视频", "4. 导出视频", "6. 导出视频"],
    detail: "页图 + 配音 + 字幕 + 背景音乐 -> MP4",
    color: "#7a5a23",
    bgcolor: "#251b0d",
    accent: "#ffd166",
    size: [620, 535],
  },
};

function injectThemeStyles() {
  if (document.getElementById("openmaic-node-theme")) return;
  const link = document.createElement("link");
  link.id = "openmaic-node-theme";
  link.rel = "stylesheet";
  link.href = "/extensions/ComfyUI-OpenMAIC-Nodes/openmaic_theme.css";
  document.head.appendChild(link);
}

function findWidget(node, name) {
  return node.widgets?.find((widget) => widget.name === name);
}

function hasInput(node, name) {
  return Boolean(node.inputs?.some((input) => input.name === name));
}

function findInput(node, name) {
  return node.inputs?.find((input) => input.name === name);
}

function markCanvasDirty(node) {
  if (typeof node.setDirtyCanvas === "function") {
    node.setDirtyCanvas(true, true);
    return;
  }
  if (typeof node.graph?.setDirtyCanvas === "function") {
    node.graph.setDirtyCanvas(true, true);
    return;
  }
  app.graph?.setDirtyCanvas?.(true, true);
}

function pickCoursewareFiles(kind) {
  return new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.style.display = "none";
    input.accept =
      kind === "folder"
        ? ".png,.jpg,.jpeg,.webp,.bmp,.gif"
        : ".pptx,.ppt,.pdf,.png,.jpg,.jpeg,.webp,.bmp,.gif";
    if (kind === "folder") {
      input.multiple = true;
      input.webkitdirectory = true;
    }
    input.onchange = () => {
      const files = Array.from(input.files || []);
      input.remove();
      resolve(files);
    };
    input.oncancel = () => {
      input.remove();
      resolve([]);
    };
    document.body.appendChild(input);
    input.click();
  });
}

async function uploadCourseware(kind, files) {
  const form = new FormData();
  form.append("kind", kind);
  for (const file of files) {
    form.append("files", file, file.webkitRelativePath || file.name);
  }
  const response = await api.fetchApi(`/openmaic_standalone/upload_courseware?kind=${kind}`, {
    method: "POST",
    body: form,
  });
  const text = await response.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { error: text };
  }
  if (!response.ok) {
    throw new Error(data?.error || "上传课件失败");
  }
  return data?.path || "";
}

function setPathWidget(node, path) {
  const widget = findWidget(node, "课件路径");
  if (!widget) return;
  widget.value = path;
  widget.callback?.(path, node, widget);
  markCanvasDirty(node);
}

function addBrowseButton(node, label, kind) {
  const button = node.addWidget("button", label, null, async () => {
    if (button.__openmaicBusy) return;
    button.__openmaicBusy = true;
    const originalLabel = button.name;
    button.name = "正在选择...";
    markCanvasDirty(node);
    try {
      const files = await pickCoursewareFiles(kind);
      if (!files.length) return;
      button.name = "正在上传...";
      markCanvasDirty(node);
      const path = await uploadCourseware(kind, files);
      if (path) setPathWidget(node, path);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      alert(`OpenMAIC 浏览课件失败：${message}`);
    } finally {
      button.name = originalLabel;
      button.__openmaicBusy = false;
      markCanvasDirty(node);
    }
  });
}

function isDefaultTitle(node, profile) {
  const title = String(node.title || "");
  return !title || profile.defaultTitles.includes(title);
}

function addPolishNote(node, profile) {
  if (node.__openmaicPolishNote || typeof node.addDOMWidget !== "function") return;
  const note = document.createElement("div");
  note.className = "openmaic-node-note";
  note.style.setProperty("--openmaic-accent", profile.accent);
  note.innerHTML = `
    <span class="openmaic-node-note__badge">${profile.step}</span>
    <span class="openmaic-node-note__text">${profile.detail}</span>
  `;
  try {
    node.addDOMWidget("OpenMAIC step note", "openmaic_note", note, {
      serialize: false,
      hideOnZoom: false,
      getMinHeight: () => 38,
      getMaxHeight: () => 38,
    });
    node.__openmaicPolishNote = true;
  } catch {
    node.__openmaicPolishNote = false;
  }
}

function installStepBadge(node, profile) {
  if (node.__openmaicStepBadge) return;
  const originalDrawForeground = node.onDrawForeground;
  node.onDrawForeground = function (ctx, ...args) {
    const result = originalDrawForeground?.apply(this, [ctx, ...args]);
    try {
      const width = this.size?.[0] || 0;
      ctx.save();
      ctx.globalAlpha = 0.95;
      ctx.fillStyle = profile.accent;
      ctx.strokeStyle = "rgba(255,255,255,0.28)";
      ctx.lineWidth = 1;
      const chipWidth = 34;
      const chipHeight = 18;
      const x = Math.max(8, width - chipWidth - 12);
      const y = -26;
      if (typeof ctx.roundRect === "function") {
        ctx.beginPath();
        ctx.roundRect(x, y, chipWidth, chipHeight, 6);
        ctx.fill();
        ctx.stroke();
      } else {
        ctx.fillRect(x, y, chipWidth, chipHeight);
        ctx.strokeRect(x, y, chipWidth, chipHeight);
      }
      ctx.fillStyle = "#071015";
      ctx.font = "bold 11px sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(profile.step, x + chipWidth / 2, y + chipHeight / 2 + 0.5);
      ctx.restore();
    } catch {
      ctx.restore?.();
    }
    return result;
  };
  node.__openmaicStepBadge = true;
}

function polishStandaloneNode(node, nodeName) {
  const profile = NODE_POLISH[nodeName];
  if (!profile) return;
  node.color = profile.color;
  node.bgcolor = profile.bgcolor;
  if (isDefaultTitle(node, profile)) {
    node.title = profile.title;
  }
  node.properties = node.properties || {};
  node.properties.openmaic_step = profile.step;
  node.properties.openmaic_detail = profile.detail;
  const width = Math.max(node.size?.[0] || 0, profile.size[0]);
  const height = Math.max(node.size?.[1] || 0, profile.size[1]);
  node.size = [width, height];
  addPolishNote(node, profile);
  installStepBadge(node, profile);
}

function migrateExportVideoNode(node) {
  let changed = false;
  const legacyAudioInput = findInput(node, "背景音乐音频");
  if (legacyAudioInput) {
    legacyAudioInput.name = "背景音乐";
    legacyAudioInput.type = "AUDIO";
    changed = true;
  }
  if (!hasInput(node, "背景音乐")) {
    node.addInput("背景音乐", "AUDIO");
    changed = true;
  }
  const legacyPathWidget = findWidget(node, "背景音乐");
  if (legacyPathWidget) {
    legacyPathWidget.name = "背景音乐路径";
    changed = true;
  }
  if (!findWidget(node, "背景音乐循环到结尾")) {
    node.addWidget("toggle", "背景音乐循环到结尾", true, () => {
      markCanvasDirty(node);
    });
    changed = true;
  }
  if (!findWidget(node, "片段并发数")) {
    node.addWidget("number", "片段并发数", 2, () => {
      markCanvasDirty(node);
    }, { min: 1, max: 4, step: 1, precision: 0 });
    changed = true;
  }
  if (changed) {
    const width = Math.max(node.size?.[0] || 580, 580);
    const height = Math.max(node.size?.[1] || 430, 470);
    node.size = [width, height];
    markCanvasDirty(node);
  }
}

function migrateGenerateScriptNode(node) {
  if (findWidget(node, "并发数")) return;
  node.addWidget("number", "并发数", 4, () => {
    markCanvasDirty(node);
  }, { min: 1, max: 16, step: 1, precision: 0 });
  node.size = [
    Math.max(node.size?.[0] || 560, 560),
    Math.max(node.size?.[1] || 390, 420),
  ];
  markCanvasDirty(node);
}

function migrateBatchTTSNode(node) {
  if (findWidget(node, "并发数")) return;
  node.addWidget("number", "并发数", 1, () => {
    markCanvasDirty(node);
  }, { min: 1, max: 16, step: 1, precision: 0 });
  node.size = [
    Math.max(node.size?.[0] || 520, 520),
    Math.max(node.size?.[1] || 360, 390),
  ];
  markCanvasDirty(node);
}

function migrateStandaloneNode(node, nodeName) {
  if (nodeName === "OpenMAICStandaloneGenerateScript") {
    migrateGenerateScriptNode(node);
  }
  if (nodeName === "OpenMAICStandaloneBatchTTS") {
    migrateBatchTTSNode(node);
  }
  if (nodeName === "OpenMAICStandaloneExportVideo") {
    migrateExportVideoNode(node);
  }
}

app.registerExtension({
  name: "OpenMAIC.Standalone.CoursewareBrowser",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!STANDALONE_NODE_TYPES.includes(nodeData.name)) return;
    injectThemeStyles();
    const original = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function (...args) {
      const result = original?.apply(this, args);
      if (nodeData.name === "OpenMAICStandaloneImportCourseware" && !this.__openmaicCoursewareBrowser) {
        this.__openmaicCoursewareBrowser = true;
        addBrowseButton(this, "浏览课件文件", "file");
        addBrowseButton(this, "浏览图片目录", "folder");
      }
      migrateStandaloneNode(this, nodeData.name);
      polishStandaloneNode(this, nodeData.name);
      return result;
    };

    const originalConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function (...args) {
      const result = originalConfigure?.apply(this, args);
      migrateStandaloneNode(this, nodeData.name);
      polishStandaloneNode(this, nodeData.name);
      return result;
    };
  },
});
