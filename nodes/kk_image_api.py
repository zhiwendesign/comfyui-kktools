import base64
import io
import json
import time

import numpy as np
import requests
import torch
from PIL import Image


class KKImageAPIRequestError(Exception):
    def __init__(self, raw_info):
        super().__init__(raw_info)
        self.raw_info = raw_info


class kkImageAPI:
    BASE_URL = "https://www.mindapi.cc/v1"
    MODEL = "gpt-image-2"
    TIMEOUT = 180
    INITIAL_POLL_DELAY = 10
    POLL_INTERVAL = 5
    RESOLUTION_OPTIONS = ["1k", "2k", "4k"]
    ASPECT_RATIO_OPTIONS = [
        "auto",
        "1:1",
        "3:2",
        "2:3",
        "16:9",
        "9:16",
        "5:4",
        "4:5",
        "4:3",
        "3:4",
        "21:9",
        "9:21",
        "1:3",
        "3:1",
        "2:1",
        "1:2",
    ]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "placeholder": "输入图片编辑提示词",
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "输入 API Key",
                }),
                "resolution": (cls.RESOLUTION_OPTIONS, {
                    "default": "1k",
                }),
                "aspect_ratio": (cls.ASPECT_RATIO_OPTIONS, {
                    "default": "auto",
                }),
            },
            "optional": {
                "image": ("IMAGE",),
            }
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "raw_info")
    FUNCTION = "generate_image"
    CATEGORY = "🌟kktools/图像"

    def generate_image(self, text, api_key, resolution="1k", aspect_ratio="auto", image=None):
        prompt = str(text or "").strip()
        key = str(api_key or "").strip()
        resolution = self._resolve_resolution(resolution)
        ratio = self._resolve_aspect_ratio(aspect_ratio)

        if not prompt:
            return (self._fallback_tensor(image), self._error_info("text is empty"))
        if not key:
            return (self._fallback_tensor(image), self._error_info("api_key is empty"))

        if image is None:
            try:
                output_image, raw_info = self._call_text_to_image_api(prompt, key, resolution, ratio)
                return (self._pil_to_tensor([output_image]), raw_info)
            except KKImageAPIRequestError as exc:
                return (self._fallback_tensor(image), exc.raw_info)
            except Exception as exc:
                return (self._fallback_tensor(image), self._error_info(str(exc)))

        input_images = self._tensor_to_pil(image)
        output_images = []
        raw_infos = []

        for index, input_image in enumerate(input_images):
            try:
                output_image, raw_info = self._call_image_edit_api(prompt, key, input_image, resolution, ratio)
                output_images.append(output_image)
                raw_infos.append(raw_info)
            except KKImageAPIRequestError as exc:
                output_images.append(input_image.convert("RGB"))
                raw_infos.append(exc.raw_info)
            except Exception as exc:
                output_images.append(input_image.convert("RGB"))
                raw_infos.append(self._error_info(str(exc), batch_index=index))

        output_tensor = self._pil_to_tensor(output_images)
        return (output_tensor, self._merge_raw_infos(raw_infos))

    def _call_text_to_image_api(self, prompt, api_key, resolution, aspect_ratio):
        url = f"{self.BASE_URL.rstrip('/')}/images/generations"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = self._build_payload(prompt, resolution, aspect_ratio)
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=self.TIMEOUT,
        )

        return self._parse_or_poll_response(response, api_key)

    def _call_image_edit_api(self, prompt, api_key, image, resolution, aspect_ratio):
        url = f"{self.BASE_URL.rstrip('/')}/images/edits"
        headers = {
            "Authorization": f"Bearer {api_key}",
        }
        data = self._build_payload(prompt, resolution, aspect_ratio)

        files = {
            "image": ("image.png", self._pil_to_png_bytes(image), "image/png"),
        }

        response = requests.post(
            url,
            headers=headers,
            data=data,
            files=files,
            timeout=self.TIMEOUT,
        )

        return self._parse_or_poll_response(response, api_key)

    def _build_payload(self, prompt, resolution, aspect_ratio):
        payload = {
            "model": self.MODEL,
            "prompt": prompt,
            "n": 1,
            "response_format": "url",
            "resolution": resolution,
        }
        if aspect_ratio != "auto":
            payload["size"] = aspect_ratio

        return payload

    def _parse_or_poll_response(self, response, api_key):
        raw_text = response.text

        if not response.ok:
            raise KKImageAPIRequestError(
                self._api_error_info("API request failed", response.status_code, raw_text)
            )

        try:
            result = response.json()
        except ValueError as exc:
            raise KKImageAPIRequestError(
                self._api_error_info(
                    "API response is not valid JSON",
                    response.status_code,
                    raw_text,
                )
            ) from exc

        try:
            output_image = self._image_from_openai_compatible_result(result)
            return output_image, raw_text
        except KKImageAPIRequestError:
            raise
        except ValueError:
            pass

        task_id = self._extract_task_id(result)
        if task_id:
            return self._poll_image_task(task_id, api_key, raw_text)

        raise KKImageAPIRequestError(
            self._api_error_info("API response has no image data or task id", response.status_code, raw_text)
        )

    def _poll_image_task(self, task_id, api_key, initial_raw_text):
        url = f"{self.BASE_URL.rstrip('/')}/tasks/{task_id}"
        headers = {
            "Authorization": f"Bearer {api_key}",
        }
        start_time = time.time()
        last_raw_text = initial_raw_text
        first_query = True

        while time.time() - start_time < self.TIMEOUT:
            if first_query:
                time.sleep(self.INITIAL_POLL_DELAY)
                first_query = False
            else:
                time.sleep(self.POLL_INTERVAL)
            response = requests.get(url, headers=headers, timeout=self.TIMEOUT)
            last_raw_text = response.text

            if not response.ok:
                raise KKImageAPIRequestError(
                    self._api_error_info("Task status request failed", response.status_code, last_raw_text)
                )

            try:
                result = response.json()
            except ValueError as exc:
                raise KKImageAPIRequestError(
                    self._api_error_info("Task status response is not valid JSON", response.status_code, last_raw_text)
                ) from exc

            try:
                output_image = self._image_from_openai_compatible_result(result)
                return output_image, self._task_raw_info(initial_raw_text, last_raw_text)
            except KKImageAPIRequestError:
                raise
            except ValueError:
                pass

            status = self._extract_status(result)
            if status in {"completed", "succeeded", "success", "done"}:
                raise KKImageAPIRequestError(
                    self._api_error_info("Image generation task completed but returned no image", response.status_code, last_raw_text)
                )

            if status in {"failed", "cancelled", "canceled", "error"}:
                raise KKImageAPIRequestError(
                    self._api_error_info("Image generation task failed", response.status_code, last_raw_text)
                )

        raise KKImageAPIRequestError(
            self._api_error_info("Image generation task timed out", 408, last_raw_text)
        )

    def _resolve_resolution(self, resolution):
        resolution = str(resolution or "auto").strip()

        if resolution in self.RESOLUTION_OPTIONS:
            return resolution

        return "1k"

    def _resolve_aspect_ratio(self, aspect_ratio):
        aspect_ratio = str(aspect_ratio or "auto").strip()
        if aspect_ratio in self.ASPECT_RATIO_OPTIONS:
            return aspect_ratio

        return "auto"

    def _extract_task_id(self, result):
        if not isinstance(result, dict):
            return None

        for key in ("id", "task_id", "taskId", "task"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        data = result.get("data")
        if isinstance(data, dict):
            for key in ("id", "task_id", "taskId", "task"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        elif isinstance(data, list):
            for item in data:
                task_id = self._extract_task_id(item)
                if task_id:
                    return task_id

        return None

    def _extract_status(self, result):
        if not isinstance(result, dict):
            return ""

        for container in (result, result.get("data"), result.get("result")):
            if isinstance(container, dict):
                value = container.get("status")
                if value is not None:
                    return str(value).lower()

        return ""

    def _image_from_openai_compatible_result(self, result):
        if isinstance(result, list):
            for item in result:
                try:
                    return self._image_from_image_item(item)
                except ValueError:
                    continue
            raise ValueError("API response list has no image data.")

        if not isinstance(result, dict):
            raise ValueError("API response is not an object.")

        for key in ("data", "output", "images", "image_urls", "urls"):
            value = result.get(key)
            if isinstance(value, list) and value:
                for item in value:
                    try:
                        return self._image_from_image_item(item)
                    except ValueError:
                        continue
            elif value:
                try:
                    return self._image_from_image_item(value)
                except ValueError:
                    try:
                        return self._image_from_openai_compatible_result(value)
                    except ValueError:
                        pass

        for key in ("b64_json", "url", "image_url", "image"):
            value = result.get(key)
            if value:
                return self._image_from_image_item(value)

        for key in ("result", "response"):
            value = result.get(key)
            if value:
                try:
                    return self._image_from_openai_compatible_result(value)
                except ValueError:
                    pass

        raise ValueError("API response has no image data.")

    def _image_from_image_item(self, item):
        if isinstance(item, dict):
            for key in ("b64_json", "base64", "image_base64"):
                value = item.get(key)
                if value:
                    return self._pil_from_b64_json(value)

            for key in ("url", "image_url", "image"):
                value = item.get(key)
                if isinstance(value, list) and value:
                    return self._image_from_image_item(value[0])
                if isinstance(value, str) and value:
                    return self._pil_from_image_string(value)

            for key in ("data", "result", "output", "images", "image_urls", "urls"):
                value = item.get(key)
                if value:
                    try:
                        return self._image_from_openai_compatible_result(value)
                    except ValueError:
                        pass

            raise ValueError("Image item has no supported image field.")

        if isinstance(item, str) and item:
            return self._pil_from_image_string(item)

        raise ValueError("Image item is not supported.")

    def _pil_from_image_string(self, value):
        value = value.strip()
        if value.startswith("http://") or value.startswith("https://"):
            return self._pil_from_url(value)

        return self._pil_from_b64_json(value)

    def _pil_from_b64_json(self, b64_json):
        if "," in b64_json and b64_json.strip().startswith("data:"):
            b64_json = b64_json.split(",", 1)[1]

        image_bytes = base64.b64decode(b64_json)
        return Image.open(io.BytesIO(image_bytes)).convert("RGB")

    def _pil_from_url(self, image_url):
        response = requests.get(image_url, timeout=self.TIMEOUT)
        if not response.ok:
            raise KKImageAPIRequestError(
                self._api_error_info("Image URL download failed", response.status_code, response.text)
            )

        return Image.open(io.BytesIO(response.content)).convert("RGB")

    def _tensor_to_pil(self, image_tensor):
        if image_tensor.ndim == 3:
            image_tensor = image_tensor.unsqueeze(0)

        images = []
        for tensor_image in image_tensor:
            image_np = tensor_image.detach().cpu().numpy()
            image_np = np.clip(image_np * 255.0, 0, 255).astype(np.uint8)
            if image_np.shape[-1] == 1:
                image_np = image_np.reshape(image_np.shape[0], image_np.shape[1])
            elif image_np.shape[-1] == 4:
                image_np = image_np[:, :, :4]
            else:
                image_np = image_np[:, :, :3]

            images.append(Image.fromarray(image_np).convert("RGB"))

        return images

    def _pil_to_tensor(self, images):
        tensors = []
        for image in images:
            image_np = np.array(image.convert("RGB")).astype(np.float32) / 255.0
            tensors.append(torch.from_numpy(image_np)[None,])

        if not tensors:
            return torch.zeros((1, 512, 512, 3))

        return torch.cat(tensors, dim=0)

    def _pil_to_png_bytes(self, image):
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="PNG")
        return buffer.getvalue()

    def _merge_raw_infos(self, raw_infos):
        if len(raw_infos) == 1:
            return raw_infos[0]

        merged = []
        for raw_info in raw_infos:
            try:
                merged.append(json.loads(raw_info))
            except (TypeError, ValueError):
                merged.append(raw_info)

        return json.dumps(
            {
                "batch_size": len(raw_infos),
                "responses": merged,
            },
            ensure_ascii=False,
        )

    def _task_raw_info(self, initial_raw_text, final_raw_text):
        return json.dumps(
            {
                "initial_response": self._json_or_text(initial_raw_text),
                "final_response": self._json_or_text(final_raw_text),
            },
            ensure_ascii=False,
        )

    def _json_or_text(self, raw_text):
        try:
            return json.loads(raw_text)
        except (TypeError, ValueError):
            return raw_text

    def _fallback_tensor(self, image=None):
        if image is not None:
            return image

        return torch.zeros((1, 512, 512, 3), dtype=torch.float32)

    def _error_info(self, message, batch_index=None):
        payload = {
            "error": message,
            "model": self.MODEL,
            "base_url": self.BASE_URL,
        }
        if batch_index is not None:
            payload["batch_index"] = batch_index
        return json.dumps(payload, ensure_ascii=False)

    def _api_error_info(self, message, status_code, response_text):
        return json.dumps(
            {
                "error": message,
                "status_code": status_code,
                "response": response_text,
            },
            ensure_ascii=False,
        )


NODE_CLASS_MAPPINGS = {
    "kkImageAPI": kkImageAPI,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "kkImageAPI": "kk-image api（图像API）",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
