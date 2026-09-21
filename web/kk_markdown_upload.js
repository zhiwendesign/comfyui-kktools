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
      const folderWidget = this.widgets?.find((widget) => widget.name === "folder_path");
      const archiveWidget = this.widgets?.find((widget) => widget.name === "archive_file");

      const upload = async (accept, targetWidget) => {
        const picker = document.createElement("input");
        picker.type = "file";
        picker.accept = accept;
        picker.onchange = async () => {
          const file = picker.files?.[0];
          if (!file) return;

          const form = new FormData();
          form.append("file", file, file.name);
          const response = await api.fetchApi("/kktools/upload_markdown", { method: "POST", body: form });
          const data = await response.json();
          if (!response.ok) {
            app.ui.dialog.show(data.error || "文件上传失败。");
            return;
          }
          if (targetWidget) {
            for (const widget of [pathWidget, folderWidget, archiveWidget]) {
              if (widget && widget !== targetWidget) {
                widget.value = "";
                widget.callback?.("");
              }
            }
            targetWidget.value = data.filename;
            targetWidget.callback?.(data.filename);
          }
          this.graph?.setDirtyCanvas?.(true, true);
          app.graph?.setDirtyCanvas?.(true, true);
          app.graph?.change?.();
          this.setDirtyCanvas(true, true);
        };
        picker.click();
      };

      this.addWidget("button", "选择并上传 MD 文件", null, async () => {
        await upload(".md,text/markdown,text/plain", pathWidget);
      });
      this.addWidget("button", "选择并上传 ZIP 压缩包", null, async () => {
        await upload(".zip,application/zip", archiveWidget);
      });
      return result;
    };
  },
});
