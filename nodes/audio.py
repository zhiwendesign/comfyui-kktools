import torch


class kkAudioMerge4:
    """
    将 4 路 AUDIO 输入按顺序拼接为 1 路 AUDIO 输出。
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "optional": {
                "audio1": ("AUDIO",),
                "audio2": ("AUDIO",),
                "audio3": ("AUDIO",),
                "audio4": ("AUDIO",),
            }
        }

    RETURN_TYPES = ("AUDIO",)
    RETURN_NAMES = ("audio",)
    FUNCTION = "merge_audio"
    CATEGORY = "kktools/音频"

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

        try:
            import torchaudio
        except ImportError as exc:
            raise ImportError(
                f"检测到不同采样率 {source_rate} -> {target_rate}，但当前环境未安装 torchaudio，无法自动重采样。"
            ) from exc

        return torchaudio.functional.resample(waveform, source_rate, target_rate)

    def _match_channels(self, waveform, target_channels, input_name):
        current_channels = waveform.shape[1]
        if current_channels == target_channels:
            return waveform

        if current_channels == 1:
            return waveform.repeat(1, target_channels, 1)

        raise ValueError(
            f"{input_name} 的声道数为 {current_channels}，无法自动匹配到目标声道数 {target_channels}。"
        )

    def _match_batch(self, waveform, target_batch, input_name):
        current_batch = waveform.shape[0]
        if current_batch == target_batch:
            return waveform

        if current_batch == 1:
            return waveform.repeat(target_batch, 1, 1)

        raise ValueError(
            f"{input_name} 的 batch 数量为 {current_batch}，无法自动匹配到目标 batch 数量 {target_batch}。"
        )

    def merge_audio(self, audio1=None, audio2=None, audio3=None, audio4=None):
        audio_inputs = [audio1, audio2, audio3, audio4]
        connected_audios = [
            (audio, f"audio{i}")
            for i, audio in enumerate(audio_inputs, start=1)
            if audio is not None
        ]

        if not connected_audios:
            raise ValueError("至少需要输入 1 路音频。")

        parsed = [
            self._get_audio_parts(audio, input_name)
            for audio, input_name in connected_audios
        ]

        target_sample_rate = parsed[0][1]
        target_channels = max(waveform.shape[1] for waveform, _ in parsed)
        target_batch = max(waveform.shape[0] for waveform, _ in parsed)

        merged_parts = []
        for (audio, input_name), (waveform, sample_rate) in zip(connected_audios, parsed):
            waveform = self._resample_waveform(waveform, sample_rate, target_sample_rate)
            waveform = self._match_channels(waveform, target_channels, input_name)
            waveform = self._match_batch(waveform, target_batch, input_name)
            merged_parts.append(waveform)

        merged_waveform = torch.cat(merged_parts, dim=-1)
        return ({"waveform": merged_waveform, "sample_rate": target_sample_rate},)
