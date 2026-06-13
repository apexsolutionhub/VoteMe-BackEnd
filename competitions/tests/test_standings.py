from django.test import TestCase

from competitions.standings import build_competition_standings
from competitions.tests.factories import (
    create_test_candidate,
    create_test_competition,
    create_test_org,
    create_test_video,
)


class StandingsTests(TestCase):
    def test_standings_ranks_by_engagement(self):
        org = create_test_org()
        competition = create_test_competition(org, status="live")
        _, leader = create_test_candidate(org, username="leader")
        _, runner = create_test_candidate(org, username="runner")

        create_test_video(
            competition,
            leader,
            views=9000,
            likes=400,
            url="https://tiktok.com/leader",
        )
        create_test_video(
            competition,
            runner,
            views=1000,
            likes=40,
            url="https://tiktok.com/runner",
        )

        standings = build_competition_standings(competition)
        self.assertEqual(standings["total_candidates"], 2)
        self.assertEqual(standings["winner"]["username"], "leader")
        self.assertEqual(standings["candidates"][0]["rank"], 1)
