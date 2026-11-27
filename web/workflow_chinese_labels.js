import { app } from "../../scripts/app.js";

const LABELS = {
  LoadImage: { image: "图片", upload: "上传图片", "choose file to upload": "选择图片", IMAGE: "图像", MASK: "蒙版" },
  kkMiniCPMLoader: {
    model: "模型", url: "服务地址", keep_alive_seconds: "模型保留时间（秒）",
    context_length: "上下文长度", max_tokens: "最大输出长度", temperature: "温度",
    seed: "种子", timeout_seconds: "超时时间（秒）", custom_model: "自定义模型",
    backend: "服务类型", connection: "模型连接", model_name: "模型名称",
    control_after_generate: "生成后的种子",
  },
  kkMiniCPMVision: {
    connection: "模型连接", image: "商品图片", prompt: "商品分析提示词",
    max_dimension: "图片最长边", description: "分析结果",
  },
  kkMiniCPMText: {
    connection: "模型连接", text: "输入文本", instruction: "提取指令", response: "提取结果",
  },
  PreviewAny: { source: "输入内容", STRING: "文本" },
  UNETLoader: { unet_name: "扩散模型", weight_dtype: "权重精度", MODEL: "模型" },
  CLIPLoader: { clip_name: "文本编码器", type: "模型类型", device: "运行设备", CLIP: "文本编码器" },
  VAELoader: { vae_name: "VAE 模型", VAE: "VAE" },
  QwenImage21Cache: { model: "模型", device: "运行设备", dtype: "数据精度", MODEL: "模型" },
  TextEncodeQwenImage21: {
    clip: "文本编码器", "images.image_1": "商品参考图 1", "images.image_2": "商品参考图 2",
    "images.image_3": "商品参考图 3", "images.image_4": "商品参考图 4",
    vae: "VAE", prompt: "正向提示词", negative_prompt: "负向提示词",
    resolution: "参考图分辨率", positive: "正向条件", negative: "负向条件", latent: "潜空间",
  },
  KSampler: {
    model: "模型", positive: "正向条件", negative: "负向条件", latent_image: "潜空间",
    seed: "种子", control_after_generate: "生成后的种子", steps: "采样步数",
    cfg: "提示词引导系数", sampler_name: "采样器", scheduler: "调度器",
    denoise: "降噪强度", LATENT: "潜空间",
  },
  VAEDecode: { samples: "潜空间", vae: "VAE", IMAGE: "图像" },
  SaveImage: { images: "图像", filename_prefix: "文件名前缀" },
};

function localize(node) {
  if (!node?.properties?.kkChineseLabels) return;
  const labels = LABELS[node.comfyClass || node.type || node.constructor?.comfyClass];
  if (!labels) return;
  for (const widget of node.widgets || []) {
    if (labels[widget.name]) widget.label = labels[widget.name];
  }
  for (const port of [...(node.inputs || []), ...(node.outputs || [])]) {
    if (labels[port.name]) {
      port.label = labels[port.name];
      port.localized_name = labels[port.name];
    }
  }
  node.setDirtyCanvas?.(true, true);
}

app.registerExtension({
  name: "kktools.workflow-chinese-labels",
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (!LABELS[nodeData.name]) return;
    const configured = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function (...args) {
      const result = configured?.apply(this, args);
      localize(this);
      requestAnimationFrame(() => localize(this));
      return result;
    };
    const changed = nodeType.prototype.onConnectionsChange;
    nodeType.prototype.onConnectionsChange = function (...args) {
      const result = changed?.apply(this, args);
      if (this.properties?.kkChineseLabels) requestAnimationFrame(() => localize(this));
      return result;
    };
  },
  loadedGraphNode: localize,
  nodeCreated: localize,
});
