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
  if (klass === "kkimage2_灵思API" || klass === "kkLingsiNativePromptImage") {
    return THEME.lingsi;
  }
  return null;
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
