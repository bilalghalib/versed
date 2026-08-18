"""Optional local multilingual semantic evidence."""

from __future__ import annotations

import math
from collections.abc import Sequence

from .dp import SpanScorer
from .scoring import estimate_length_ratio

DEFAULT_SEMANTIC_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class TransformerEmbedder:
    """Transformers wrapper with remote model code disabled and exact-text caching."""

    def __init__(
        self,
        model_name_or_path: str = DEFAULT_SEMANTIC_MODEL,
        *,
        batch_size: int = 32,
        max_length: int = 256,
        local_files_only: bool = False,
        device: str = "auto",
        context_threshold: float = 0.62,
        context_margin: float = 0.025,
        position_penalty: float = 0.08,
    ) -> None:
        if batch_size <= 0 or max_length <= 0:
            raise ValueError("batch_size and max_length must be positive")
        if not 0 <= context_threshold <= 1 or context_margin < 0 or position_penalty < 0:
            raise ValueError("semantic context parameters are out of range")
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "semantic alignment requires the 'semantic' extra: "
                "pip install 'versed-pdf[semantic]'"
            ) from exc
        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(
            model_name_or_path,
            trust_remote_code=False,
            local_files_only=local_files_only,
        )
        self._model = AutoModel.from_pretrained(
            model_name_or_path,
            trust_remote_code=False,
            local_files_only=local_files_only,
        )
        if device == "auto":
            if torch.backends.mps.is_available():
                device = "mps"
            elif torch.cuda.is_available():
                device = "cuda"
            else:
                device = "cpu"
        if device not in {"cpu", "mps", "cuda"}:
            raise ValueError("semantic device must be auto, cpu, mps, or cuda")
        self.device = device
        self._model.to(device)
        self._model.eval()
        self.batch_size = batch_size
        self.max_length = max_length
        self.model_name = model_name_or_path
        self.context_threshold = context_threshold
        self.context_margin = context_margin
        self.position_penalty = position_penalty
        self.waypoint_count = 0
        self._cache: dict[str, tuple[float, ...]] = {}

    def encode(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        missing = [text for text in dict.fromkeys(texts) if text not in self._cache]
        torch = self._torch
        for start in range(0, len(missing), self.batch_size):
            batch = missing[start:start + self.batch_size]
            encoded = self._tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=self.max_length,
                return_tensors="pt",
            )
            encoded = {key: value.to(self.device) for key, value in encoded.items()}
            with torch.inference_mode():
                output = self._model(**encoded).last_hidden_state
                mask = encoded["attention_mask"].unsqueeze(-1).to(output.dtype)
                pooled = (output * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1)
                pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
            for text, vector in zip(batch, pooled.cpu().tolist()):
                self._cache[text] = tuple(float(value) for value in vector)
        return [self._cache[text] for text in texts]

    def scorer(self, arabic: list[str], english: list[str]) -> SpanScorer:
        ar_vectors = self.encode(arabic)
        en_vectors = self.encode(english)
        ratio = estimate_length_ratio(arabic, english)
        torch = self._torch
        ar_tensor = torch.tensor(ar_vectors, dtype=torch.float32)
        en_tensor = torch.tensor(en_vectors, dtype=torch.float32)
        max_span = 5

        def spans(values, width: int):
            if width > len(values):
                return None
            prefix = torch.cat(
                (torch.zeros((1, values.shape[1]), dtype=values.dtype), values.cumsum(dim=0)),
                dim=0,
            )
            output = prefix[width:] - prefix[:-width]
            return torch.nn.functional.normalize(output, p=2, dim=1)

        ar_spans = {width: spans(ar_tensor, width) for width in range(1, max_span + 1)}
        en_spans = {width: spans(en_tensor, width) for width in range(1, max_span + 1)}
        similarities = {
            (ar_width, en_width): (ar_values @ en_values.T).numpy()
            for ar_width, ar_values in ar_spans.items()
            for en_width, en_values in en_spans.items()
            if ar_values is not None and en_values is not None
        }
        waypoints = _context_waypoints(
            similarities.get((3, 3)),
            threshold=self.context_threshold,
            margin=self.context_margin,
        )
        self.waypoint_count += len(waypoints)
        ar_word_prefix = [0]
        en_word_prefix = [0]
        for value in arabic:
            ar_word_prefix.append(ar_word_prefix[-1] + len(value.split()))
        for value in english:
            en_word_prefix.append(en_word_prefix[-1] + len(value.split()))

        def score(
            ar_items: list[str], ar_start: int, ar_end: int,
            en_items: list[str], en_start: int, en_end: int,
        ) -> float:
            ar_width = ar_end - ar_start
            en_width = en_end - en_start
            cosine = float(similarities[(ar_width, en_width)][ar_start, en_start])
            ar_words = ar_word_prefix[ar_end] - ar_word_prefix[ar_start]
            en_words = en_word_prefix[en_end] - en_word_prefix[en_start]
            expected = max(1.0, ar_words * ratio)
            length_cost = abs(math.log(max(1.0, en_words) / expected))
            position_cost = _position_cost(
                (ar_start + ar_end - 1) / 2,
                (en_start + en_end - 1) / 2,
                waypoints,
            )
            return (
                2.7 * cosine
                - 0.45 * length_cost
                - self.position_penalty * position_cost
                - 1.0
            )

        return score


def _context_waypoints(matrix, *, threshold: float, margin: float) -> tuple[tuple[float, float], ...]:
    """Find strong mutual context matches, then keep the best monotone chain."""
    if matrix is None or not matrix.size or matrix.shape[0] < 2 or matrix.shape[1] < 2:
        return ()
    candidates: list[tuple[int, int, float]] = []
    column_best = matrix.argmax(axis=0)
    for ar_start, row in enumerate(matrix):
        order = row.argsort()
        en_start = int(order[-1])
        best = float(row[en_start])
        second = float(row[int(order[-2])])
        evidence_margin = best - second
        if (
            best >= threshold
            and evidence_margin >= margin
            and int(column_best[en_start]) == ar_start
        ):
            candidates.append((ar_start + 1, en_start + 1, best + evidence_margin))
    if not candidates:
        return ()

    best_scores = [value[2] for value in candidates]
    previous: list[int | None] = [None] * len(candidates)
    for index, (ar_position, en_position, weight) in enumerate(candidates):
        for earlier in range(index):
            earlier_ar, earlier_en, _ = candidates[earlier]
            if earlier_ar < ar_position and earlier_en < en_position:
                score = best_scores[earlier] + weight
                if score > best_scores[index]:
                    best_scores[index] = score
                    previous[index] = earlier
    cursor = max(range(len(candidates)), key=best_scores.__getitem__)
    chain: list[tuple[float, float]] = []
    while cursor is not None:
        ar_position, en_position, _ = candidates[cursor]
        chain.append((float(ar_position), float(en_position)))
        cursor = previous[cursor]
    chain.reverse()
    return tuple(chain)


def _position_cost(
    arabic_position: float,
    english_position: float,
    waypoints: tuple[tuple[float, float], ...],
) -> float:
    """Distance from the piecewise-linear path; outside anchors, make no promise."""
    for left, right in zip(waypoints, waypoints[1:]):
        ar_left, en_left = left
        ar_right, en_right = right
        if ar_left <= arabic_position <= ar_right and ar_right > ar_left:
            fraction = (arabic_position - ar_left) / (ar_right - ar_left)
            expected = en_left + fraction * (en_right - en_left)
            return abs(english_position - expected)
    return 0.0
