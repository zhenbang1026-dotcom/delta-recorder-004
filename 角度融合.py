from __future__ import annotations

import math
from dataclasses import dataclass


class 角度融合失败(RuntimeError):
    pass


@dataclass(frozen=True)
class 角度观测:
    angle: float
    confidence: float = 1.0
    source: str = ""


@dataclass(frozen=True)
class 角度融合结果:
    angle: float
    source: str
    confidence: float
    reason: str


def _角差绝对值(a: float, b: float) -> float:
    return abs((float(b) - float(a) + 180.0) % 360.0 - 180.0)


class 角度融合选择器:
    """TEXT 主观测、Legacy 故障降级的带迟滞选择器。"""

    def __init__(
        self,
        *,
        agreement_threshold: float = 12.0,
        innovation_margin: float = 8.0,
        min_confidence: float = 0.5,
        text_recovery_confirm: int = 3,
        hold_limit: int = 0,
    ) -> None:
        self.agreement_threshold = float(agreement_threshold)
        self.innovation_margin = float(innovation_margin)
        self.min_confidence = float(min_confidence)
        self.text_recovery_confirm = max(1, int(text_recovery_confirm))
        self.hold_limit = max(0, int(hold_limit))
        self.reset()

    def reset(self) -> None:
        self.active_source: str | None = None
        self.last_angle: float | None = None
        self._text_recovery_count = 0
        self._hold_count = 0

    def force(self, angle: float) -> float:
        self.last_angle = float(angle) % 360.0
        self._hold_count = 0
        return self.last_angle

    def _valid(self, observation: 角度观测 | None) -> 角度观测 | None:
        if observation is None:
            return None
        if not math.isfinite(float(observation.angle)):
            return None
        if not math.isfinite(float(observation.confidence)):
            return None
        if float(observation.confidence) < self.min_confidence:
            return None
        return 角度观测(
            float(observation.angle) % 360.0,
            min(1.0, max(0.0, float(observation.confidence))),
            observation.source,
        )

    def _emit(self, observation: 角度观测, source: str, reason: str) -> 角度融合结果:
        self.active_source = source
        self.last_angle = observation.angle
        self._hold_count = 0
        if source != "legacy":
            self._text_recovery_count = 0
        return 角度融合结果(observation.angle, source, observation.confidence, reason)

    def update(
        self,
        text: 角度观测 | None,
        legacy: 角度观测 | None,
        *,
        predicted_angle: float | None = None,
    ) -> 角度融合结果:
        text = self._valid(text)
        legacy = self._valid(legacy)
        if text is None and legacy is None:
            self._text_recovery_count = 0
            if self.last_angle is not None and self._hold_count < self.hold_limit:
                self._hold_count += 1
                return 角度融合结果(self.last_angle, "hold", 0.0, "双路失败，短时保持")
            raise 角度融合失败("TEXT 与 Legacy 均无法提供可信角度")
        if text is None:
            self._text_recovery_count = 0
            return self._emit(legacy, "legacy", "TEXT 无效，降级 Legacy")
        if legacy is None:
            return self._emit(text, "text", "Legacy 无效，采用 TEXT")

        if _角差绝对值(text.angle, legacy.angle) <= self.agreement_threshold:
            候选来源 = "text"
            原因 = "双路一致，采用 TEXT"
        else:
            参考角 = predicted_angle if predicted_angle is not None else self.last_angle
            if 参考角 is None:
                候选来源 = self.active_source or "legacy"
            else:
                text创新 = _角差绝对值(参考角, text.angle)
                legacy创新 = _角差绝对值(参考角, legacy.angle)
                if text创新 + self.innovation_margin < legacy创新:
                    候选来源 = "text"
                elif legacy创新 + self.innovation_margin < text创新:
                    候选来源 = "legacy"
                else:
                    候选来源 = "legacy"
            原因 = "双路分歧，按预测连续性选择"

        if 候选来源 == "text" and self.active_source == "legacy":
            self._text_recovery_count += 1
            if self._text_recovery_count < self.text_recovery_confirm:
                return self._emit(legacy, "legacy", "TEXT 恢复确认中")
        else:
            self._text_recovery_count = 0
        if 候选来源 == "text":
            return self._emit(text, "text", 原因)
        return self._emit(legacy, "legacy", 原因)
