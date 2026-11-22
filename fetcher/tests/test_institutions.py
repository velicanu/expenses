import pytest
from fetcher import institutions as inst
from fetcher.institutions import (
    CHALLENGE,
    LOGGED_IN,
    LOGIN_REQUIRED,
    UNKNOWN,
    PageFacts,
    classify_venmo,
)


def facts(url, status=200, title="", text="", password=False):
    return PageFacts(
        url=url, status=status, title=title, text=text, has_password_field=password
    )


def test_venmos_human_check_is_a_challenge_not_a_login_page():
    """What the probe saw on 2026-11-22: a 403 with a 'Confirm you're human' slider, before any login form."""
    f = facts(
        "https://id.venmo.com/signin?country.x=US",
        status=403,
        title="venmo.com",
        text="Confirm you’re human\nMove the slider all the way to the right",
    )
    assert classify_venmo(f) == CHALLENGE


def test_a_challenge_is_a_challenge_even_with_a_200_or_on_the_logged_in_host():
    assert (
        classify_venmo(
            facts(
                "https://account.venmo.com/statement",
                text="Please verify you are human",
            )
        )
        == CHALLENGE
    )
    assert (
        classify_venmo(facts("https://id.venmo.com/signin", text="Are you a human?"))
        == CHALLENGE
    )
    assert classify_venmo(facts("https://account.venmo.com/", status=403)) == CHALLENGE


def test_the_sign_in_page_means_a_login_is_needed():
    assert (
        classify_venmo(
            facts("https://id.venmo.com/signin", title="Sign in", password=True)
        )
        == LOGIN_REQUIRED
    )
    assert (
        classify_venmo(facts("https://account.venmo.com/", title="Sign in to Venmo"))
        == LOGIN_REQUIRED
    )
    assert (
        classify_venmo(facts("https://account.venmo.com/statement", password=True))
        == LOGIN_REQUIRED
    )


def test_the_statements_page_means_logged_in():
    assert (
        classify_venmo(
            facts(
                "https://account.venmo.com/statement",
                title="Statements",
                text="Statements\nMarch 2026",
            )
        )
        == LOGGED_IN
    )
    assert (
        classify_venmo(
            facts("https://account.venmo.com/", title="Venmo", text="Your feed")
        )
        == LOGGED_IN
    )


def test_anything_else_is_unknown():
    assert classify_venmo(facts("https://example.com/")) == UNKNOWN


def test_exit_codes_tell_the_states_apart_and_success_is_zero():
    codes = inst.EXIT_CODES
    assert codes[LOGGED_IN] == 0
    assert len(set(codes.values())) == 4 and set(codes) == {
        LOGGED_IN,
        LOGIN_REQUIRED,
        CHALLENGE,
        UNKNOWN,
    }


def test_the_registry_knows_venmo_and_refuses_others_clearly():
    v = inst.get("venmo")
    assert (
        v.home_url.startswith("https://account.venmo.com/")
        and v.classify is classify_venmo
    )
    with pytest.raises(SystemExit) as e:
        inst.get("nowhere")
    assert "venmo" in str(e.value)
