from tests.factories import make_repo
from tests.fakes import FakeLLM
from weekly_ai_newsletter.services.repo_curator import RepoCurator, RepoVerdict, RepoVerdicts

REPOS = [
    make_repo("a/slow", stars_this_week=100),
    make_repo("b/fast", stars_this_week=900),
    make_repo("c/hype", stars_this_week=5000),
]


def test_keeps_validated_repos_ranked_by_stars_gained() -> None:
    verdicts = RepoVerdicts(
        verdicts=[
            RepoVerdict(full_name="a/slow", keep=True, why_interesting="Useful."),
            RepoVerdict(full_name="b/fast", keep=True, why_interesting="Great."),
            RepoVerdict(full_name="c/hype", keep=False, why_interesting=""),
            RepoVerdict(full_name="z/invented", keep=True, why_interesting="?"),
        ]
    )
    curator = RepoCurator(FakeLLM({RepoVerdicts: verdicts}), language="en", max_items=5)
    curated = curator.curate(REPOS)
    assert [c.repo.full_name for c in curated] == ["b/fast", "a/slow"]
    assert curated[0].why_interesting == "Great."


def test_caps_number_of_repos() -> None:
    verdicts = RepoVerdicts(
        verdicts=[RepoVerdict(full_name=r.full_name, keep=True, why_interesting="x") for r in REPOS]
    )
    curator = RepoCurator(FakeLLM({RepoVerdicts: verdicts}), language="en", max_items=2)
    assert [c.repo.full_name for c in curator.curate(REPOS)] == ["c/hype", "b/fast"]
