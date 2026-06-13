from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from competitions.eligibility import (
    INELIGIBILITY_AFTER_END,
    INELIGIBILITY_BEFORE_START,
    INELIGIBILITY_NOT_STARTED,
    compute_video_eligibility,
    reevaluate_competition_videos,
)
from competitions.tests.factories import (
    create_test_candidate,
    create_test_competition,
    create_test_org,
    create_test_video,
)


class EligibilityTests(TestCase):
    def test_video_before_competition_start_is_ineligible(self):
        org = create_test_org()
        start = timezone.now()
        competition = create_test_competition(org, start_at=start)
        _, profile = create_test_candidate(org)
        video = create_test_video(
            competition,
            profile,
            platform_published_at=start - timedelta(hours=2),
        )

        eligible, reason = compute_video_eligibility(video)
        self.assertFalse(eligible)
        self.assertEqual(reason, INELIGIBILITY_BEFORE_START)

    def test_video_after_competition_end_is_ineligible(self):
        org = create_test_org(slug="ended-org")
        start = timezone.now() - timedelta(days=3)
        end = timezone.now() - timedelta(days=1)
        competition = create_test_competition(org, start_at=start, end_at=end, status="ended")
        _, profile = create_test_candidate(org, username="ended-user")
        video = create_test_video(
            competition,
            profile,
            platform_published_at=timezone.now(),
        )

        eligible, reason = compute_video_eligibility(video)
        self.assertFalse(eligible)
        self.assertEqual(reason, INELIGIBILITY_AFTER_END)

    def test_video_in_window_is_eligible(self):
        org = create_test_org(slug="live-org")
        start = timezone.now() - timedelta(days=1)
        competition = create_test_competition(org, start_at=start)
        _, profile = create_test_candidate(org, username="live-user")
        video = create_test_video(
            competition,
            profile,
            platform_published_at=timezone.now() - timedelta(hours=1),
        )

        eligible, reason = compute_video_eligibility(video)
        self.assertTrue(eligible)
        self.assertEqual(reason, "")

    def test_draft_competition_marks_videos_ineligible(self):
        org = create_test_org(slug="draft-org")
        competition = create_test_competition(org, status="draft")
        competition.start_at = None
        competition.save(update_fields=["start_at"])
        _, profile = create_test_candidate(org, username="draft-user")
        video = create_test_video(competition, profile)

        eligible, reason = compute_video_eligibility(video)
        self.assertFalse(eligible)
        self.assertEqual(reason, INELIGIBILITY_NOT_STARTED)

    def test_reevaluate_updates_flags(self):
        org = create_test_org(slug="reeval-org")
        start = timezone.now()
        competition = create_test_competition(org, start_at=start)
        _, profile = create_test_candidate(org, username="reeval-user")
        video = create_test_video(
            competition,
            profile,
            platform_published_at=start - timedelta(hours=1),
        )

        reevaluate_competition_videos(competition)
        video.refresh_from_db()
        self.assertFalse(video.is_competition_eligible)
        self.assertEqual(video.ineligibility_reason, INELIGIBILITY_BEFORE_START)
