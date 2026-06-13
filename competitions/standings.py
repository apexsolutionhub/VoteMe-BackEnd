from __future__ import annotations

from competitions.criteria import (
    build_criteria_achievements,
    ensure_default_criteria,
    get_field_metric_stats,
)
from competitions.leaderboard import aggregate_candidate_leaderboard_rows
from competitions.models import CandidateProfile, Competition


def _aggregate_candidate_rows(competition: Competition) -> list[dict]:
    return aggregate_candidate_leaderboard_rows(competition)


def _candidate_totals(entry: dict) -> dict:
    return {
        "views": entry["views"],
        "likes": entry["likes"],
        "comments": entry["comments"],
        "shares": entry["shares"],
        "brand_mention_comments": entry["brand_mention_comments"],
        "engagement_score": entry["engagement_score"],
    }


def _profile_stub(entry: dict) -> CandidateProfile:
    profile = CandidateProfile(
        id=entry["candidate_id"],
        is_profile_complete=entry["is_profile_complete"],
    )
    return profile


def build_competition_standings(competition: Competition) -> dict:
    ensure_default_criteria(competition)
    field_stats = get_field_metric_stats(competition)
    entries = _aggregate_candidate_rows(competition)

    candidate_rows: list[dict] = []
    achievements_by_criterion: dict[int, list[dict]] = {}

    for entry in entries:
        profile = _profile_stub(entry)
        totals = _candidate_totals(entry)
        achievements = build_criteria_achievements(
            competition,
            profile,
            totals,
            video_count=entry["video_count"],
            rank=entry["rank"],
        )
        unlocked = sum(1 for item in achievements if item.get("unlocked"))

        candidate_rows.append(
            {
                **entry,
                "milestones_unlocked": unlocked,
                "milestones_total": len(achievements),
                "milestone_progress": (
                    round((unlocked / len(achievements)) * 100) if achievements else 0
                ),
                "achievements": achievements,
            }
        )

        for achievement in achievements:
            criterion_id = achievement.get("criterion_id")
            if criterion_id is None:
                continue
            achievements_by_criterion.setdefault(criterion_id, []).append(
                {
                    "candidate_id": entry["candidate_id"],
                    "name": entry["name"],
                    "username": entry["username"],
                    "initials": entry["initials"],
                    "profile_image_url": entry["profile_image_url"],
                    "rank": entry["rank"],
                    "current": achievement.get("current"),
                    "target": achievement.get("target"),
                    "unlocked": achievement.get("unlocked", False),
                }
            )

    milestones = list(
        competition.criteria.filter(
            kind="milestone",
            is_active=True,
        ).order_by("sort_order", "id")
    )

    criteria_outcomes: list[dict] = []
    for criterion in milestones:
        holders = [
            item
            for item in achievements_by_criterion.get(criterion.id, [])
            if item["unlocked"]
        ]
        all_attempts = achievements_by_criterion.get(criterion.id, [])

        if criterion.evaluation_mode == "relative":
            leader_value = field_stats.get(f"{criterion.metric_key}_max", 0.0)
            leaders = [
                item
                for item in all_attempts
                if leader_value > 0
                and item.get("current") is not None
                and float(item["current"]) >= leader_value
                and float(item["current"]) > 0
            ]
            if not leaders and all_attempts:
                leaders = sorted(
                    all_attempts,
                    key=lambda item: float(item.get("current") or 0),
                    reverse=True,
                )[:1]

            status = "leading" if leaders else "open"
            criteria_outcomes.append(
                {
                    "criterion_id": criterion.id,
                    "title": criterion.title,
                    "description": criterion.description,
                    "evaluation_mode": criterion.evaluation_mode,
                    "metric_key": criterion.metric_key,
                    "status": status,
                    "holders": leaders,
                }
            )
            continue

        status = "awarded" if holders else "open"
        criteria_outcomes.append(
            {
                "criterion_id": criterion.id,
                "title": criterion.title,
                "description": criterion.description,
                "evaluation_mode": criterion.evaluation_mode,
                "metric_key": criterion.metric_key,
                "target_value": criterion.target_value,
                "status": status,
                "holders": holders,
            }
        )

    winner = candidate_rows[0] if candidate_rows else None

    return {
        "final_award": competition.final_award,
        "competition_status": competition.status,
        "winner": winner,
        "criteria_outcomes": criteria_outcomes,
        "candidates": candidate_rows,
        "total_candidates": len(candidate_rows),
    }
