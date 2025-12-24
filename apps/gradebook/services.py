# apps/gradebook/services.py
from decimal import Decimal
from typing import Iterable, Optional, Tuple
from .models import Assessment, Grade


def compute_average_percent(assessments: Iterable[Assessment], grades_by_assessment_id: dict) -> Optional[Decimal]:
    """
    Weighted average in percent:
    sum((score/max_score)*weight) / sum(weight) * 100
    Only counts assessments where score is not None.
    """
    total_weight = Decimal("0")
    total = Decimal("0")

    for a in assessments:
        g: Grade | None = grades_by_assessment_id.get(a.id)
        if not g or g.score is None:
            continue
        if a.max_score == 0:
            continue
        frac = (Decimal(g.score) / Decimal(a.max_score))
        total += frac * Decimal(a.weight)
        total_weight += Decimal(a.weight)

    if total_weight == 0:
        return None

    return (total / total_weight) * Decimal("100")
