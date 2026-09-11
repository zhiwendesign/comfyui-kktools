import { app } from "/scripts/app.js";
import { api } from "/scripts/api.js";

app.registerExtension({
  name: "kktools.markdownUpload",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== "kkMarkdown上传") return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const result = onNodeCreated?.apply(this, arguments);
      const pathWidget = this.widgets?.find((widget) => widget.name === "markdown_file");

      this.addWidget("button", "选择并上传 MD 文件", null, async () => {
        const picker = document.createElement("input");
        picker.type = "file";
        picker.accept = ".md,text/markdown,text/plain";
        picker.onchange = async () => {
          const file = picker.files?.[0];
          if (!file) return;

          const form = new FormData();
          form.append("file", file, file.name);
          const response = await api.fetchApi("/kktools/upload_markdown", {
            method: "POST",
            body: form,
          });
          const data = await response.json();
          if (!response.ok) {
            app.ui.dialog.show(data.error || "Markdown 文件上传失败。");
            return;
          }
          if (pathWidget) {
            pathWidget.value = data.filename;
            pathWidget.callback?.(data.filename);
          }
          this.setDirtyCanvas(true, true);
        };
        picker.click();
      });
      return result;
    };
  },
});
