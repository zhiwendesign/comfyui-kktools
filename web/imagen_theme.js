import { app } from "../../scripts/app.js";

const PIPE_TYPES = ["IMAGEN_STUDIO_PIPE", "IMAGEN_PPT_PIPE"];
const PIPE_PURPLE = "#7737AA";
const STYLE_ID = "imagen-studio-theme-style";

const THEME = {
  template: { color: "#56306f", bgcolor: "rgba(18, 18, 24, 0.96)" },
  ppt: { color: "#37376f", bgcolor: "rgba(17, 18, 27, 0.96)" },
  runninghub: { color: "#4d3478", bgcolor: "rgba(18, 18, 24, 0.96)" },
  lingsi: { color: "#3b426f", bgcolor: "rgba(17, 18, 27, 0.96)" },
};

const CATEGORY_THEMES = {
  "🌟kktools/图像": { color: "#255f66", bgcolor: "rgba(15, 24, 27, 0.96)" },
  "🌟kktools/数学计算": { color: "#35558a", bgcolor: "rgba(16, 20, 30, 0.96)" },
  "🌟kktools/提示词": { color: "#644481", bgcolor: "rgba(22, 17, 29, 0.96)" },
  "🌟kktools/尺寸": { color: "#2e607e", bgcolor: "rgba(15, 22, 28, 0.96)" },
  "🌟kktools/字符串": { color: "#3c6b55", bgcolor: "rgba(16, 24, 20, 0.96)" },
  "🌟kktools/随机": { color: "#7a5830", bgcolor: "rgba(27, 22, 15, 0.96)" },
  "🌟kktools/视频": { color: "#7a3f55", bgcolor: "rgba(28, 17, 22, 0.96)" },
  "🌟kktools/音频": { color: "#7b4b32", bgcolor: "rgba(28, 20, 16, 0.96)" },
  "🌟kktools/分镜": { color: "#654368", bgcolor: "rgba(25, 18, 27, 0.96)" },
  "🌟kktools/兼容": { color: "#4b5563", bgcolor: "rgba(21, 23, 27, 0.96)" },
  "OpenMAIC/导入": { color: "#315f72", bgcolor: "rgba(15, 23, 27, 0.96)" },
  "OpenMAIC/独立版": { color: "#4d4f7c", bgcolor: "rgba(18, 19, 28, 0.96)" },
  "OpenMAIC/导出": { color: "#5f4a73", bgcolor: "rgba(23, 18, 27, 0.96)" },
  "OpenMAIC/音频": { color: "#6c5032", bgcolor: "rgba(26, 21, 16, 0.96)" },
  "OpenMAIC/工具": { color: "#3e6260", bgcolor: "rgba(16, 24, 23, 0.96)" },
};

function nodeClass(node) {
  return node?.comfyClass || node?.type || node?.constructor?.comfyClass || "";
}

function nodeCategory(node) {
  return node?.constructor?.nodeData?.category || node?.nodeData?.category || "";
}

function addStyles() {
  if (document.getElementById(STYLE_ID)) {
    return;
  }
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .imagen-template-selector,
    .imagen-status {
      --imagen-accent: ${PIPE_PURPLE};
      --imagen-panel-bg: rgba(18, 18, 24, 0.96);
      --imagen-panel-border: rgba(119, 55, 170, 0.45);
    }

    .imagen-template-selector {
      background: linear-gradient(180deg, rgba(25, 24, 31, 0.98), rgba(16, 16, 21, 0.98));
      border-color: var(--imagen-panel-border);
    }

    .imagen-template-selector button:hover,
    .imagen-template-selector .is-selected {
      border-color: var(--imagen-accent);
    }

    .imagen-status {
      border-color: var(--imagen-panel-border);
      background: rgba(18, 18, 24, 0.92);
    }
  `;
  document.head.appendChild(style);
}

function registerPipeColors() {
  for (const type of PIPE_TYPES) {
    if (app?.canvas?.default_connection_color_byType) {
      app.canvas.default_connection_color_byType[type] = PIPE_PURPLE;
    }
    if (globalThis.LGraphCanvas?.link_type_colors) {
      globalThis.LGraphCanvas.link_type_colors[type] = PIPE_PURPLE;
    }
  }
}

function themeForNode(node) {
  const klass = nodeClass(node);
  if (klass.startsWith("ImagenStudioPPT")) {
    return THEME.ppt;
  }
  if (klass === "ImagenStudioRunningHubRHArtG2") {
    return THEME.runninghub;
  }
  if (klass.startsWith("ImagenStudio")) {
    return THEME.template;
  }
  if (klass === "kkGPT-image_API") {
    return THEME.lingsi;
  }
  return CATEGORY_THEMES[nodeCategory(node)] || null;
}

function applyNodeTheme(node) {
  const theme = themeForNode(node);
  if (!theme) {
    return;
  }
  node.color = theme.color;
  node.bgcolor = theme.bgcolor;
}

app.registerExtension({
  name: "kktools.imagen.theme",
  setup() {
    addStyles();
    registerPipeColors();
  },
  nodeCreated(node) {
    registerPipeColors();
    applyNodeTheme(node);
  },
});
