# Aliased imports: pytest would otherwise try to collect Test*-named classes.
from test_verification.domain.models import TestResult as Result
from test_verification.domain.models import TestSuite as Suite


def test_suite_passes_only_when_all_results_pass():
    passing = Suite(name="auth", results=(Result("a", True), Result("b", True)))
    failing = Suite(
        name="auth",
        results=(Result("a", True), Result("b", False, output="boom")),
    )
    assert passing.passed
    assert not failing.passed


def test_empty_suite_does_not_pass():
    assert not Suite(name="empty").passed
