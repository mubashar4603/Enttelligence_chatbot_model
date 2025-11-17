#!/usr/bin/env python3
"""
Quick diagnostic tool to verify comp-title logic.

Usage examples:

    # Test a single movie
    python3 manage.py test_comp_titles --title "Twisters" --limit 5

    # Test a few key titles (Twisters, Dune, Joker, etc.)
    python3 manage.py test_comp_titles --preset core
"""

from django.core.management.base import BaseCommand

from movies.performance_service import MoviePerformanceService


DEFAULT_PRESET_TITLES = [
    "Twisters",
    "Dune: Part Two",
    "Homestead",
    "Joker: Folie a Deux",
    "Monkey Man",
    "Five Nights at Freddy's 2",
]


class Command(BaseCommand):
    help = "Test which movies are performing like a given movie (comp titles) using day-over-day growth logic."

    def add_arguments(self, parser):
        parser.add_argument(
            "--title",
            type=str,
            default=None,
            help="Target movie title to analyze (exact match used in DB).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=5,
            help="Number of comp titles to display (default: 5).",
        )
        parser.add_argument(
            "--preset",
            type=str,
            default=None,
            help="Optional preset group of titles to test (e.g. 'core' = key studio titles).",
        )

    def handle(self, *args, **options):
        target_title = options.get("title")
        limit = options.get("limit") or 5
        preset = options.get("preset")

        service = MoviePerformanceService()

        titles_to_test = []
        if target_title:
            titles_to_test.append(target_title)
        elif preset == "core":
            titles_to_test.extend(DEFAULT_PRESET_TITLES)
        else:
            self.stdout.write(
                self.style.ERROR(
                    "You must provide --title or use --preset core (Twisters, Dune, Joker, etc.)."
                )
            )
            return

        for title in titles_to_test:
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS(f"🎯 Testing comp titles for: {title}"))

            try:
                result = service.find_best_comp_titles_by_trajectory(
                    target_title=title,
                    limit=limit,
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"   ✗ Error analyzing '{title}': {e}")
                )
                continue

            candidates = result.get("candidates", [])
            valid_candidates = result.get("valid_candidates", [])

            if not candidates:
                self.stdout.write(
                    self.style.WARNING("   ⚠️  No comp candidates found for this title.")
                )
                continue

            self.stdout.write(
                f"   Total candidates evaluated: {len(candidates)} | "
                f"Valid matches: {len(valid_candidates)}"
            )

            for idx, comp in enumerate(candidates, start=1):
                comp_title = comp.get("title", "Unknown")
                similarity = comp.get("trend_similarity", 0.0)
                growth_sim = comp.get(
                    "growth_rate_similarity", comp.get("trend_similarity", 0.0)
                )
                overlap_ratio = comp.get("overlap_ratio", 0.0)
                revenue_ratio = comp.get("revenue_ratio", 0.0)
                valid = comp.get("valid_comp", False)
                reasons = comp.get("reasons", [])

                status = "✅ VALID" if valid else "❌ REJECTED"

                self.stdout.write(
                    f"   {idx}. {comp_title} [{status}] "
                    f"(growth_sim={growth_sim:.2f}, overlap={overlap_ratio:.0%}, "
                    f"revenue_ratio={revenue_ratio:.2f}x)"
                )

                if reasons:
                    for r in reasons:
                        self.stdout.write(f"        - {r}")


