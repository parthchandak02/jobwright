"""Retrieve the candidate's most similar past decisions as few-shot examples.

Pure-Python TF-IDF over title + company + the start of the description. No
embedding API: the label set is small (hundreds) and this runs in milliseconds.
Leave-one-out is supported so offline evals never show a job its own label.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from jobwright.discovery.dedupe import normalize_company, normalize_title
from jobwright.labels import EvalItem

_TOKEN = re.compile(r"[a-z][a-z0-9+&'-]{1,}")
_STOP = frozenset(
    "the and for with you our are will this that from have your their who all can not has but its into "
    "about more also they them than such what when which while where work team role job jobs position "
    "including include including experience years strong ability skills new help support".split()
)


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall((text or "").lower()) if t not in _STOP]


def _doc(item: EvalItem) -> list[str]:
    title = _tokens(item.title)
    # Title words matter most for "is this the same kind of role".
    return title * 3 + _tokens(item.company) + _tokens(item.description[:1500])


@dataclass
class Example:
    item: EvalItem
    similarity: float


class ExampleIndex:
    def __init__(self, items: list[EvalItem]) -> None:
        self.items = [i for i in items if i.title]
        docs = [Counter(_doc(i)) for i in self.items]
        df: Counter[str] = Counter()
        for d in docs:
            df.update(d.keys())
        n = max(1, len(docs))
        self._idf = {t: math.log((n + 1) / (c + 1)) + 1.0 for t, c in df.items()}
        self._vecs = [self._weigh(d) for d in docs]
        # company|title identity: reposts of the same opening share it, so
        # leave-one-out can exclude every copy of the job being judged.
        self._idents = [f"{normalize_company(i.company)}|{normalize_title(i.title)}" for i in self.items]

    def _weigh(self, counts: Counter[str]) -> dict[str, float]:
        vec = {t: (1 + math.log(c)) * self._idf.get(t, 1.0) for t, c in counts.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {t: v / norm for t, v in vec.items()}

    def query(
        self,
        title: str,
        company: str,
        description: str,
        *,
        k: int = 8,
        exclude_urls: set[str] | None = None,
        exclude_keys: set[str] | None = None,
        min_positive: int = 2,
    ) -> list[Example]:
        """Top-k similar decisions, keeping at least ``min_positive`` relevant ones.

        Positives are rare; without a floor the block would be all rejections and
        the model would learn to reject everything.
        """
        if not self.items:
            return []
        probe = EvalItem("", title, company, "", description, "", 0, "", None, "", None, None)
        q = self._weigh(Counter(_doc(probe)))
        exclude_urls = exclude_urls or set()
        exclude_keys = {k for k in (exclude_keys or set()) if k}
        scored: list[Example] = []
        for item, vec, ident in zip(self.items, self._vecs, self._idents):
            if item.url in exclude_urls or ident in exclude_keys:
                continue
            sim = sum(w * vec.get(t, 0.0) for t, w in q.items())
            scored.append(Example(item, sim))
        scored.sort(key=lambda e: e.similarity, reverse=True)
        top = scored[:k]
        have_pos = sum(1 for e in top if e.item.label == 1)
        if have_pos < min_positive:
            extra = [e for e in scored[k:] if e.item.label == 1][: min_positive - have_pos]
            if extra:
                negatives = [e for e in top if e.item.label == 0]
                keep_neg = negatives[: max(0, k - have_pos - len(extra))]
                top = [e for e in top if e.item.label == 1] + extra + keep_neg
                top.sort(key=lambda e: e.similarity, reverse=True)
        return top


def render_examples(examples: list[Example]) -> str:
    if not examples:
        return ""
    lines = ["THIS CANDIDATE'S PAST DECISIONS ON SIMILAR POSTINGS (follow their taste):"]
    for ex in examples:
        it = ex.item
        where = f", {it.location}" if it.location else ""
        head = f"{it.title} @ {it.company or 'unknown'}{where}"
        if it.label == 1:
            verdict = "APPLIED / WANTED" if it.source != "label" else f"WANTED (rated {it.label_score}/10)"
        else:
            verdict = f"REJECTED (rated {it.label_score}/10)" if it.label_score else "REJECTED (closed without applying)"
        why = f' — "{it.rationale.strip()[:160]}"' if it.rationale.strip() else ""
        lines.append(f"- {verdict}: {head}{why}")
    return "\n".join(lines)
