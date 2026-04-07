import torch
import torch.nn.functional as torch_functional


class _VideoNodeMixin:
    def _get_video_components(self, video):
        if hasattr(video, "get_components") and callable(video.get_components):
            return video.get_components()
        if isinstance(video, dict):
            return video
        raise TypeError("video 必须是 ComfyUI 的 VIDEO 类型。")

    def _extract_images(self, video, components=None):
        components = components if components is not None else self._get_video_components(video)
        images = getattr(components, "images", None) if not isinstance(components, dict) else components.get("images")

        if images is None:
            raise ValueError("无法从 VIDEO 输入中提取图像帧。")

        if not isinstance(images, torch.Tensor):
            raise TypeError("VIDEO 中的 images 必须是 torch.Tensor。")

        if images.ndim == 3:
            images = images.unsqueeze(0)

        if images.ndim != 4:
            raise ValueError(
                f"VIDEO 中的 images 需要是 4 维张量 [frames, height, width, channels]，当前维度: {tuple(images.shape)}"
            )

        if images.shape[0] < 1:
            raise ValueError("video 至少需要包含 1 帧。")

        return images

    def _extract_fps(self, video, components=None):
        fps = None

        if hasattr(video, "get_frame_rate") and callable(video.get_frame_rate):
            fps = video.get_frame_rate()
        else:
            components = components if components is not None else self._get_video_components(video)
            if isinstance(components, dict):
                fps = components.get("frame_rate", components.get("fps"))
            else:
                fps = getattr(components, "frame_rate", None)

        if fps is None:
            raise ValueError("无法从 VIDEO 输入中获取 FPS。")

        fps_value = float(fps)
        if fps_value <= 0:
            raise ValueError(f"VIDEO 的 FPS 必须大于 0，当前值: {fps_value}")

        return fps_value

    def _extract_audio(self, video, components=None):
        components = components if components is not None else self._get_video_components(video)
        audio = getattr(components, "audio", None) if not isinstance(components, dict) else components.get("audio")

        if audio is None:
            return None

        if not isinstance(audio, dict):
            raise TypeError("VIDEO 中的 audio 必须是 ComfyUI 的 AUDIO 类型。")

        waveform = audio.get("waveform")
        sample_rate = audio.get("sample_rate", audio.get("sampler_rate"))

        if waveform is None or sample_rate is None:
            raise ValueError("VIDEO 中的 audio 缺少 waveform 或 sample_rate。")

        return {
            "waveform": waveform.clone() if isinstance(waveform, torch.Tensor) else waveform,
            "sample_rate": int(sample_rate),
        }

    def _get_audio_parts(self, audio, input_name):
        if not isinstance(audio, dict):
            raise TypeError(f"{input_name} 必须是 ComfyUI 的 AUDIO 类型。")

        waveform = audio.get("waveform")
        sample_rate = audio.get("sample_rate", audio.get("sampler_rate"))

        if waveform is None or sample_rate is None:
            raise ValueError(f"{input_name} 缺少 waveform 或 sample_rate。")

        if not isinstance(waveform, torch.Tensor):
            raise TypeError(f"{input_name}.waveform 必须是 torch.Tensor。")

        if waveform.ndim == 2:
            waveform = waveform.unsqueeze(0)

        if waveform.ndim != 3:
            raise ValueError(
                f"{input_name}.waveform 需要是 3 维张量 [batch, channels, samples]，当前维度: {tuple(waveform.shape)}"
            )

        sample_rate = int(sample_rate)
        if sample_rate <= 0:
            raise ValueError(f"{input_name}.sample_rate 必须大于 0，当前值: {sample_rate}")

        return waveform, sample_rate

    def _resample_waveform(self, waveform, source_rate, target_rate):
        if source_rate == target_rate:
            return waveform

        source_samples = int(waveform.shape[-1])
        if source_samples <= 0:
            return waveform

        target_samples = max(1, int(round(source_samples * float(target_rate) / float(source_rate))))
        working = waveform if waveform.is_floating_point() else waveform.float()
        resampled = torch_functional.interpolate(
            working,
            size=target_samples,
            mode="linear",
            align_corners=False,
        )

        if waveform.is_floating_point() and resampled.dtype != waveform.dtype:
            resampled = resampled.to(dtype=waveform.dtype)

        return resampled

    def _match_channels(self, waveform, target_channels, input_name):
        current_channels = int(waveform.shape[1])
        if current_channels == target_channels:
            return waveform

        if current_channels == 1:
            return waveform.repeat(1, target_channels, 1)

        raise ValueError(
            f"{input_name} 的声道数为 {current_channels}，无法自动匹配到目标声道数 {target_channels}。"
        )

    def _match_batch(self, waveform, target_batch, input_name):
        current_batch = int(waveform.shape[0])
        if current_batch == target_batch:
            return waveform

        if current_batch == 1:
            return waveform.repeat(target_batch, 1, 1)

        raise ValueError(
            f"{input_name} 的 batch 数量为 {current_batch}，无法自动匹配到目标 batch 数量 {target_batch}。"
        )

    def _duration_to_sample_count(self, duration_seconds, sample_rate):
        return max(1, int(round(float(duration_seconds) * int(sample_rate))))

    def _fit_waveform_to_sample_count(self, waveform, target_samples):
        current_samples = int(waveform.shape[-1])
        if current_samples == target_samples:
            return waveform

        if current_samples <= 0:
            return torch.zeros(
                (*waveform.shape[:2], target_samples),
                dtype=waveform.dtype if waveform.is_floating_point() else torch.float32,
                device=waveform.device,
            )

        working = waveform if waveform.is_floating_point() else waveform.float()
        resized = torch_functional.interpolate(
            working,
            size=target_samples,
            mode="linear",
            align_corners=False,
        )

        if waveform.is_floating_point() and resized.dtype != waveform.dtype:
            resized = resized.to(dtype=waveform.dtype)

        return resized


class _KKVideo:
    def __init__(self, images, frame_rate, audio=None):
        self.images = images
        self.frame_rate = float(frame_rate)
        self.audio = audio

    def get_components(self):
        try:
            from fractions import Fraction
            from comfy_api.latest import Types

            return Types.VideoComponents(
                images=self.images,
                audio=self.audio,
                frame_rate=Fraction(self.frame_rate),
            )
        except Exception:
            return self

    def get_frame_rate(self):
        return self.frame_rate

    def get_dimensions(self):
        height = int(self.images.shape[1])
        width = int(self.images.shape[2])
        return (width, height)

    def save_to(self, path, format, codec, metadata=None):
        from fractions import Fraction
        from comfy_api.latest import InputImpl, Types

        components = Types.VideoComponents(
            images=self.images,
            audio=self.audio,
            frame_rate=Fraction(self.frame_rate),
        )
        return InputImpl.VideoFromComponents(components).save_to(
            path,
            format=format,
            codec=codec,
            metadata=metadata,
        )


class kkVideoFirstLastFrames(_VideoNodeMixin):
    """
    从 ComfyUI 的 VIDEO 输入中提取首帧、尾帧，以及仅包含首尾两帧的新批次。
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("VIDEO",),
            }
        }

    RETURN_TYPES = ("IMAGE", "IMAGE", "IMAGE", "AUDIO")
    RETURN_NAMES = ("first_frame", "last_frame", "first_last_frames", "audio")
    FUNCTION = "extract_frames"
    CATEGORY = "kktools/视频"

    def extract_frames(self, video):
        components = self._get_video_components(video)
        images = self._extract_images(video, components=components)
        audio = self._extract_audio(video, components=components)

        first_frame = images[:1].clone()
        last_frame = images[-1:].clone()
        first_last_frames = torch.cat((first_frame, last_frame), dim=0)

        return (first_frame, last_frame, first_last_frames, audio)


class kkVideoFramesAdvanced(_VideoNodeMixin):
    """
    从 VIDEO 中提取全部帧，或按时间间隔抽帧，并输出 FPS 与提取信息。
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("VIDEO",),
                "extract_mode": (["every_frame", "interval_seconds"], {"default": "every_frame"}),
                "interval_seconds": ("FLOAT", {"default": 1.0, "min": 0.001, "max": 3600.0, "step": 0.1}),
            }
        }

    RETURN_TYPES = ("IMAGE", "FLOAT", "INT", "STRING")
    RETURN_NAMES = ("images", "fps", "extracted_count", "info")
    FUNCTION = "extract_frames_advanced"
    CATEGORY = "kktools/视频"

    def extract_frames_advanced(self, video, extract_mode, interval_seconds):
        components = self._get_video_components(video)
        images = self._extract_images(video, components=components)
        fps = self._extract_fps(video, components=components)

        if extract_mode == "every_frame":
            selected_images = images.clone()
            extracted_count = int(selected_images.shape[0])
            info = (
                f"模式: 每一帧 | FPS: {fps:.4f} | 原始帧数: {images.shape[0]} | 提取帧数: {extracted_count}"
            )
            return (selected_images, fps, extracted_count, info)

        frame_interval = max(1, int(round(interval_seconds * fps)))
        frame_indices = torch.arange(0, images.shape[0], frame_interval, device=images.device)
        selected_images = images.index_select(0, frame_indices).clone()
        extracted_count = int(selected_images.shape[0])

        info = (
            f"模式: 每隔 {interval_seconds:.3f} 秒 | FPS: {fps:.4f} | "
            f"步长: {frame_interval} 帧 | 原始帧数: {images.shape[0]} | 提取帧数: {extracted_count}"
        )

        return (selected_images, fps, extracted_count, info)


class kkMergeVideos(_VideoNodeMixin):
    """
    合并多个 VIDEO 输入并输出单个 VIDEO，同时按顺序拼接每段视频对应的音频。
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video1": ("VIDEO",),
                "size_reference": (
                    ["keep", "video1", "video2", "video3", "video4", "video5", "custom"],
                    {"default": "keep"},
                ),
                "width": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 8}),
                "height": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 8}),
                "fps": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 240.0, "step": 0.1}),
            },
            "optional": {
                "video2": ("VIDEO",),
                "video3": ("VIDEO",),
                "video4": ("VIDEO",),
                "video5": ("VIDEO",),
                "audio": ("AUDIO",),
            },
        }

    RETURN_TYPES = ("VIDEO",)
    RETURN_NAMES = ("video",)
    FUNCTION = "merge_videos"
    CATEGORY = "kktools/视频"

    def _resize_images(self, images, target_height, target_width):
        frames, height, width, channels = images.shape
        if height == target_height and width == target_width:
            return images
        resized = torch_functional.interpolate(
            images.permute(0, 3, 1, 2),
            size=(target_height, target_width),
            mode="bilinear",
            align_corners=False,
        )
        return resized.permute(0, 2, 3, 1)

    def _resolve_target_size(self, videos, size_reference, width, height):
        if size_reference == "keep":
            return None
        if size_reference == "custom":
            if width <= 0 or height <= 0:
                raise ValueError("size_reference=custom 时，width 和 height 必须大于 0。")
            return (height, width)

        ref_index = int(size_reference.replace("video", "")) - 1
        if ref_index < 0 or ref_index >= len(videos):
            raise ValueError(f"size_reference={size_reference} 但对应视频未连接。")

        ref_images = videos[ref_index]["images"]
        return (int(ref_images.shape[1]), int(ref_images.shape[2]))

    def _resolve_target_fps(self, videos, size_reference, fps_override):
        if fps_override > 0:
            return float(fps_override)

        if size_reference.startswith("video"):
            ref_index = int(size_reference.replace("video", "")) - 1
            if ref_index < 0 or ref_index >= len(videos):
                raise ValueError(f"size_reference={size_reference} 但对应视频未连接。")
            return float(videos[ref_index]["fps"])

        return float(videos[0]["fps"])

    def _merge_video_audios(self, videos, target_fps):
        available_audio = [
            self._get_audio_parts(entry["audio"], f"video{index}.audio")
            for index, entry in enumerate(videos, start=1)
            if entry["audio"] is not None
        ]

        if not available_audio:
            return None

        target_sample_rate = available_audio[0][1]
        target_channels = max(int(waveform.shape[1]) for waveform, _ in available_audio)
        target_batch = max(int(waveform.shape[0]) for waveform, _ in available_audio)
        base_waveform = available_audio[0][0]
        base_dtype = base_waveform.dtype if base_waveform.is_floating_point() else torch.float32
        base_device = base_waveform.device

        merged_parts = []
        for index, entry in enumerate(videos, start=1):
            segment_samples = self._duration_to_sample_count(
                float(entry["images"].shape[0]) / float(target_fps),
                target_sample_rate,
            )

            if entry["audio"] is None:
                merged_parts.append(
                    torch.zeros(
                        (target_batch, target_channels, segment_samples),
                        dtype=base_dtype,
                        device=base_device,
                    )
                )
                continue

            waveform, sample_rate = self._get_audio_parts(entry["audio"], f"video{index}.audio")
            waveform = waveform.to(device=base_device)
            if waveform.is_floating_point() and waveform.dtype != base_dtype:
                waveform = waveform.to(dtype=base_dtype)
            elif not waveform.is_floating_point():
                waveform = waveform.to(dtype=base_dtype)

            waveform = self._resample_waveform(waveform, sample_rate, target_sample_rate)
            waveform = self._match_channels(waveform, target_channels, f"video{index}.audio")
            waveform = self._match_batch(waveform, target_batch, f"video{index}.audio")
            waveform = self._fit_waveform_to_sample_count(waveform, segment_samples)
            merged_parts.append(waveform)

        merged_waveform = torch.cat(merged_parts, dim=-1)
        return {"waveform": merged_waveform, "sample_rate": target_sample_rate}

    def merge_videos(
        self,
        video1,
        size_reference,
        width,
        height,
        fps,
        video2=None,
        video3=None,
        video4=None,
        video5=None,
        audio=None,
    ):
        input_videos = [video1, video2, video3, video4, video5]
        videos = []
        for video in input_videos:
            if video is None:
                continue
            components = self._get_video_components(video)
            images = self._extract_images(video, components=components)
            fps_value = self._extract_fps(video, components=components)
            audio_value = self._extract_audio(video, components=components)
            videos.append({"images": images, "fps": fps_value, "audio": audio_value})

        if not videos:
            raise ValueError("至少需要连接一个 VIDEO 输入。")

        target_size = self._resolve_target_size(videos, size_reference, width, height)
        target_fps = self._resolve_target_fps(videos, size_reference, fps)

        if size_reference == "keep":
            first_size = (int(videos[0]["images"].shape[1]), int(videos[0]["images"].shape[2]))
            for entry in videos[1:]:
                current_size = (int(entry["images"].shape[1]), int(entry["images"].shape[2]))
                if current_size != first_size:
                    raise ValueError("size_reference=keep 时，所有视频分辨率必须一致。")
            for entry in videos[1:]:
                if float(entry["fps"]) != float(videos[0]["fps"]) and fps <= 0:
                    raise ValueError("size_reference=keep 且 fps=0 时，所有视频 FPS 必须一致。")

        processed_images = []
        for entry in videos:
            images = entry["images"]
            if target_size is not None:
                images = self._resize_images(images, target_size[0], target_size[1])
            processed_images.append(images)

        merged_images = torch.cat(processed_images, dim=0)

        output_audio = audio
        if output_audio is None:
            output_audio = self._merge_video_audios(videos, target_fps)

        return (_KKVideo(merged_images, target_fps, output_audio),)
