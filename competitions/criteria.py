from __future__ import annotations

from django.db.models import Count, Max, Sum

from competitions.eligibility import eligible_videos_filter
from competitions.models import (
    CandidateProfile,
    Competition,
    CompetitionCriterion,
    CompetitionVideo,
)

def _totals_field(metric_key: str) -> str:
    if metric_key == CompetitionCriterion.MetricKey.BRAND_MENTIONS:
        return "brand_mention_comments"
    return metric_key


WORD_WEIGHT_MAP: dict[str, float] = {
    "low": 1.0,
    "minor": 1.0,
    "light": 1.0,
    "small": 1.0,
    "medium": 3.0,
    "moderate": 3.0,
    "normal": 3.0,
    "average": 3.0,
    "high": 5.0,
    "major": 5.0,
    "strong": 5.0,
    "important": 5.0,
    "very high": 10.0,
    "very_high": 10.0,
    "critical": 10.0,
    "primary": 10.0,
    "maximum": 10.0,
    "dominant": 10.0,
}


def resolve_criterion_weight(criterion: CompetitionCriterion) -> float:
    if criterion.kind != CompetitionCriterion.Kind.METRIC:
        return 0.0

    if criterion.weight_input_type == CompetitionCriterion.WeightInputType.NUMBER:
        return max(float(criterion.weight_value or 0), 0.0)

    if criterion.weight_input_type == CompetitionCriterion.WeightInputType.WORD:
        token = (criterion.weight_display or "").strip().lower()
        if token in WORD_WEIGHT_MAP:
            return WORD_WEIGHT_MAP[token]
        return max(float(criterion.weight_value or 1), 0.0)

    return max(float(criterion.weight_value or 0), 0.0)


def build_scoring_weights(competition: Competition) -> dict[str, float]:
    metrics = list(
        competition.criteria.filter(
            kind=CompetitionCriterion.Kind.METRIC,
            is_active=True,
        ).order_by("sort_order", "id")
    )
    if not metrics:
        return competition.get_scoring_weights()

    number_weights: dict[str, float] = {}
    word_weights: dict[str, float] = {}
    percentage_items: list[tuple[str, float]] = []

    for criterion in metrics:
        key = criterion.metric_key
        if criterion.weight_input_type == CompetitionCriterion.WeightInputType.PERCENTAGE:
            percentage_items.append((key, max(float(criterion.weight_value or 0), 0.0)))
        elif criterion.weight_input_type == CompetitionCriterion.WeightInputType.WORD:
            word_weights[key] = resolve_criterion_weight(criterion)
        else:
            number_weights[key] = resolve_criterion_weight(criterion)

    weights = {**number_weights, **word_weights}

    if percentage_items:
        total_pct = sum(value for _, value in percentage_items) or 100.0
        for key, value in percentage_items:
            weights[key] = (value / total_pct) * 10.0

    if not weights:
        return competition.get_scoring_weights()

    return weights


def get_field_metric_stats(competition: Competition) -> dict[str, float]:
    rows = (
        CompetitionVideo.objects.filter(**eligible_videos_filter(competition))
        .values("candidate_profile_id")
        .annotate(
            views=Sum("views"),
            likes=Sum("likes"),
            comments=Sum("scored_comments"),
            shares=Sum("shares"),
            brand_mention_comments=Sum("brand_mention_comments"),
            engagement_score=Sum("engagement_score"),
            video_count=Count("id"),
        )
    )

    stats: dict[str, float] = {}
    metric_keys = (
        "views",
        "likes",
        "comments",
        "shares",
        "brand_mention_comments",
        "engagement_score",
        "video_count",
    )

    for key in metric_keys:
        values = [float(row.get(key) or 0) for row in rows]
        stats[f"{key}_max"] = max(values) if values else 0.0
        stats[f"{key}_min"] = min(values) if values else 0.0
        if key == "brand_mention_comments":
            stats["brand_mentions_max"] = stats[f"{key}_max"]
            stats["brand_mentions_min"] = stats[f"{key}_min"]

    complete_count = CandidateProfile.objects.filter(
        organization=competition.organization,
        is_profile_complete=True,
    ).count()
    stats["profile_complete_max"] = float(complete_count > 0)
    stats["profile_complete_count"] = float(complete_count)

    return stats


def _metric_value(
    metric_key: str,
    profile: CandidateProfile,
    totals: dict,
    *,
    video_count: int,
    rank: int | None,
) -> float:
    if metric_key == CompetitionCriterion.MetricKey.PROFILE_COMPLETE:
        return 1.0 if profile.is_profile_complete else 0.0
    if metric_key == CompetitionCriterion.MetricKey.VIDEO_COUNT:
        return float(video_count)
    if metric_key == CompetitionCriterion.MetricKey.RANK:
        return float(rank or 0)
    if metric_key == CompetitionCriterion.MetricKey.ENGAGEMENT_SCORE:
        return float(totals.get("engagement_score") or 0)
    return float(totals.get(_totals_field(metric_key)) or 0)


def _evaluate_milestone(
    criterion: CompetitionCriterion,
    profile: CandidateProfile,
    totals: dict,
    *,
    video_count: int,
    rank: int | None,
    field_stats: dict[str, float],
) -> dict:
    metric_key = criterion.metric_key
    current = _metric_value(
        metric_key,
        profile,
        totals,
        video_count=video_count,
        rank=rank,
    )

    item = {
        "id": f"criterion_{criterion.id}",
        "criterion_id": criterion.id,
        "title": criterion.title,
        "description": criterion.description,
        "kind": criterion.kind,
        "evaluation_mode": criterion.evaluation_mode,
        "metric_key": metric_key,
        "unlocked": False,
    }

    if criterion.evaluation_mode == CompetitionCriterion.EvaluationMode.RELATIVE:
        field_max = field_stats.get(f"{metric_key}_max", 0.0)
        if field_max <= 0:
            unlocked = current > 0
            progress = 100 if unlocked else 0
        else:
            unlocked = current >= field_max and current > 0
            progress = min(100, round((current / field_max) * 100))

        item["unlocked"] = unlocked
        item["current"] = current
        item["target"] = field_max
        item["progress"] = progress
        item["relative_label"] = (
            "Leading the field" if unlocked else "Compete for the top spot"
        )
        return item

    target = float(criterion.target_value or 1)
    if metric_key == CompetitionCriterion.MetricKey.PROFILE_COMPLETE:
        unlocked = profile.is_profile_complete
        item["unlocked"] = unlocked
        if not unlocked:
            item["current"] = 0
            item["target"] = 1
            item["progress"] = 0
        return item

    unlocked = current >= target
    item["unlocked"] = unlocked
    if target > 0:
        item["current"] = current
        item["target"] = target
        item["progress"] = min(100, round((current / target) * 100))
    return item


def build_criteria_achievements(
    competition: Competition,
    profile: CandidateProfile,
    totals: dict,
    *,
    video_count: int,
    rank: int | None = None,
) -> list[dict]:
    milestones = competition.criteria.filter(
        kind=CompetitionCriterion.Kind.MILESTONE,
        is_active=True,
    ).order_by("sort_order", "id")

    if not milestones.exists():
        return _legacy_achievements(profile, totals, video_count)

    field_stats = get_field_metric_stats(competition)
    return [
        _evaluate_milestone(
            criterion,
            profile,
            totals,
            video_count=video_count,
            rank=rank,
            field_stats=field_stats,
        )
        for criterion in milestones
    ]


def _legacy_achievements(
    profile: CandidateProfile,
    totals: dict,
    video_count: int,
) -> list[dict]:
    views = int(totals.get("views") or 0)
    likes = int(totals.get("likes") or 0)
    brand_mentions = int(totals.get("brand_mention_comments") or 0)

    def milestone(
        id: str,
        title: str,
        description: str,
        unlocked: bool,
        *,
        current: int | float | None = None,
        target: int | float | None = None,
        evaluation_mode: str = "absolute",
    ) -> dict:
        item = {
            "id": id,
            "title": title,
            "description": description,
            "unlocked": unlocked,
            "kind": "milestone",
            "evaluation_mode": evaluation_mode,
        }
        if current is not None and target is not None and target > 0:
            item["current"] = current
            item["target"] = target
            item["progress"] = min(100, round((current / target) * 100))
        return item

    return [
        milestone(
            "profile_complete",
            "Profile ready",
            "Complete your candidate profile to join the competition.",
            profile.is_profile_complete,
            evaluation_mode="absolute",
        ),
        milestone(
            "first_video",
            "First video live",
            "Submit at least one competition video.",
            video_count >= 1,
            current=video_count,
            target=1,
        ),
        milestone(
            "views_100",
            "100 views",
            "Reach 100 total video views.",
            views >= 100,
            current=views,
            target=100,
        ),
        milestone(
            "views_1k",
            "1K views",
            "Reach 1,000 total video views.",
            views >= 1000,
            current=views,
            target=1000,
        ),
        milestone(
            "likes_50",
            "50 likes",
            "Collect 50 likes across your videos.",
            likes >= 50,
            current=likes,
            target=50,
        ),
        milestone(
            "brand_mention",
            "Brand buzz",
            "Get a comment mentioning the brand.",
            brand_mentions >= 1,
            current=brand_mentions,
            target=1,
        ),
    ]


def ensure_default_criteria(competition: Competition) -> None:
    if competition.criteria.exists():
        return

    defaults = [
        {
            "kind": CompetitionCriterion.Kind.MILESTONE,
            "metric_key": CompetitionCriterion.MetricKey.PROFILE_COMPLETE,
            "evaluation_mode": CompetitionCriterion.EvaluationMode.ABSOLUTE,
            "title": "Profile ready",
            "description": "Complete your candidate profile to join the competition.",
            "target_value": 1,
            "sort_order": 10,
        },
        {
            "kind": CompetitionCriterion.Kind.MILESTONE,
            "metric_key": CompetitionCriterion.MetricKey.VIDEO_COUNT,
            "evaluation_mode": CompetitionCriterion.EvaluationMode.ABSOLUTE,
            "title": "First video live",
            "description": "Submit at least one competition video.",
            "target_value": 1,
            "sort_order": 20,
        },
        {
            "kind": CompetitionCriterion.Kind.MILESTONE,
            "metric_key": CompetitionCriterion.MetricKey.VIEWS,
            "evaluation_mode": CompetitionCriterion.EvaluationMode.ABSOLUTE,
            "title": "100 views",
            "description": "Reach 100 total video views.",
            "target_value": 100,
            "sort_order": 30,
        },
        {
            "kind": CompetitionCriterion.Kind.MILESTONE,
            "metric_key": CompetitionCriterion.MetricKey.LIKES,
            "evaluation_mode": CompetitionCriterion.EvaluationMode.ABSOLUTE,
            "title": "50 likes",
            "description": "Collect 50 likes across your videos.",
            "target_value": 50,
            "sort_order": 40,
        },
        {
            "kind": CompetitionCriterion.Kind.MILESTONE,
            "metric_key": CompetitionCriterion.MetricKey.BRAND_MENTIONS,
            "evaluation_mode": CompetitionCriterion.EvaluationMode.ABSOLUTE,
            "title": "Brand buzz",
            "description": "Get a comment mentioning the brand.",
            "target_value": 1,
            "sort_order": 50,
        },
    ]

    weights = competition.get_scoring_weights()
    metric_defaults = [
        ("views", weights.get("views", 1)),
        ("likes", weights.get("likes", 3)),
        ("comments", weights.get("comments", 5)),
        ("shares", weights.get("shares", 2)),
        ("brand_mentions", weights.get("brand_mentions", 10)),
    ]

    for index, payload in enumerate(defaults, start=1):
        CompetitionCriterion.objects.create(competition=competition, **payload)

    for index, (metric_key, weight) in enumerate(metric_defaults, start=1):
        CompetitionCriterion.objects.create(
            competition=competition,
            kind=CompetitionCriterion.Kind.METRIC,
            metric_key=metric_key,
            evaluation_mode=CompetitionCriterion.EvaluationMode.ABSOLUTE,
            title=metric_key.replace("_", " ").title(),
            description=f"Scoring weight for {metric_key.replace('_', ' ')}.",
            weight_value=weight,
            weight_input_type=CompetitionCriterion.WeightInputType.NUMBER,
            weight_display=str(weight),
            sort_order=index * 10,
        )
