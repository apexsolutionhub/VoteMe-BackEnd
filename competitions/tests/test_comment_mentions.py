from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from competitions.comment_mentions import (
    compute_scored_comment_count,
    count_matching_stored_comments,
    normalize_comment_match_terms,
    text_matches_comment_terms,
)
from competitions.models import Competition, VideoComment
from competitions.tests.factories import (
    create_test_candidate,
    create_test_competition,
    create_test_org,
    create_test_video,
)


class CommentMentionsTests(TestCase):
    def test_normalize_comment_match_terms(self):
        terms = normalize_comment_match_terms("@ella\n#ella, @ella")
        self.assertEqual(terms, ["@ella", "#ella"])

    def test_text_matches_comment_terms(self):
        self.assertTrue(text_matches_comment_terms("Love @ellaresort!", ["@ellaresort"]))
        self.assertFalse(text_matches_comment_terms("Nice video", ["@ellaresort"]))

    def test_matched_scoring_uses_stored_comments(self):
        org = create_test_org()
        competition = create_test_competition(org)
        competition.comment_scoring_mode = Competition.CommentScoringMode.MATCHED
        competition.comment_match_terms = ["@brand"]
        competition.save()

        _, profile = create_test_candidate(org)
        video = create_test_video(competition, profile, comments=100)
        VideoComment.objects.create(
            video=video,
            platform_comment_id="1",
            text="Hello @brand",
        )
        VideoComment.objects.create(
            video=video,
            platform_comment_id="2",
            text="No match here",
        )

        self.assertEqual(count_matching_stored_comments(video, ["@brand"]), 1)
        self.assertEqual(compute_scored_comment_count(video), 1)

    def test_matched_scoring_falls_back_without_stored_comments(self):
        org = create_test_org(slug="org-2")
        competition = create_test_competition(org)
        competition.comment_scoring_mode = Competition.CommentScoringMode.MATCHED
        competition.comment_match_terms = ["@brand"]
        competition.save()

        _, profile = create_test_candidate(org, username="c2")
        video = create_test_video(competition, profile, comments=42)

        self.assertEqual(compute_scored_comment_count(video), 42)
