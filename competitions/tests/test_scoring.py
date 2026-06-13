from django.test import TestCase

from competitions.leaderboard import build_leaderboard
from competitions.sync import calculate_engagement_score
from competitions.tests.factories import (
    create_test_candidate,
    create_test_competition,
    create_test_org,
    create_test_video,
)


class ScoringTests(TestCase):
    def test_calculate_engagement_score(self):
        weights = {
            "views": 1,
            "likes": 3,
            "comments": 5,
            "shares": 2,
            "brand_mentions": 10,
        }
        score = calculate_engagement_score(
            views=1000,
            likes=50,
            comments=10,
            shares=5,
            weights=weights,
            brand_mention_comments=2,
        )
        self.assertEqual(score, 1000 + 150 + 50 + 10 + 20)

    def test_ineligible_video_scores_zero(self):
        org = create_test_org()
        competition = create_test_competition(org)
        _, profile_a = create_test_candidate(org, username="a")
        _, profile_b = create_test_candidate(org, username="b")

        create_test_video(competition, profile_a, views=5000, likes=200, url="https://tiktok.com/a")
        create_test_video(
            competition,
            profile_b,
            views=100,
            likes=1,
            url="https://tiktok.com/b",
        )
        # Force ineligible on second video
        video_b = profile_b.videos.first()
        video_b.is_competition_eligible = False
        video_b.engagement_score = 0
        video_b.save()

        leaderboard = build_leaderboard(competition)
        self.assertEqual(len(leaderboard), 1)
        self.assertEqual(leaderboard[0]["username"], "a")
