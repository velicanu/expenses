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


# --- Wealthfront (provisional: only its sign-in page has been looked at) ----------------------------------------------


def test_wealthfronts_sign_in_page_means_a_login_is_needed():
    """The probe saw a normal 200 page with an email/password form and "Continue with passkey"."""
    cw = inst.classify_wealthfront
    assert (
        cw(
            facts(
                "https://www.wealthfront.com/login",
                title="Log in | Wealthfront",
                password=True,
            )
        )
        == LOGIN_REQUIRED
    )
    assert (
        cw(facts("https://www.wealthfront.com/login", title="Wealthfront"))
        == LOGIN_REQUIRED
    )  # passkey-only form: no password field
    assert (
        cw(facts("https://www.wealthfront.com/", title="Sign in to Wealthfront"))
        == LOGIN_REQUIRED
    )
    assert (
        cw(facts("https://www.wealthfront.com/x", title="Wealthfront", password=True))
        == LOGIN_REQUIRED
    )


def test_a_wealthfront_page_that_is_not_the_sign_in_page_counts_as_logged_in():
    cw = inst.classify_wealthfront
    assert (
        cw(facts("https://www.wealthfront.com/dashboard", title="Wealthfront"))
        == LOGGED_IN
    )
    assert (
        cw(
            facts(
                "https://www.wealthfront.com/cash/activity",
                title="Cash Account | Wealthfront",
            )
        )
        == LOGGED_IN
    )
    assert (
        cw(facts("https://app.wealthfront.com/home", title="Wealthfront")) == LOGGED_IN
    )


def test_wealthfront_challenges_and_foreign_pages_are_never_logged_in():
    cw = inst.classify_wealthfront
    assert (
        cw(
            facts(
                "https://www.wealthfront.com/login", status=403, title="Access denied"
            )
        )
        == CHALLENGE
    )
    assert (
        cw(
            facts(
                "https://www.wealthfront.com/dashboard",
                text="Please verify you are human",
            )
        )
        == CHALLENGE
    )
    assert cw(facts("https://accounts.example.com/sso", title="Wealthfront")) == UNKNOWN
    assert (
        cw(facts("https://wealthfront.com.evil.example/dashboard", title="Wealthfront"))
        == UNKNOWN
    )  # a lookalike host
    # a host that merely ENDS with the name, without the dot, is not Wealthfront either
    assert (
        cw(facts("https://evilwealthfront.com/dashboard", title="Wealthfront"))
        == UNKNOWN
    )
    assert (
        cw(facts("https://notwealthfront.com/dashboard", title="Wealthfront"))
        == UNKNOWN
    )


def test_only_venmo_has_a_downloader_so_far():
    assert inst.get("venmo").download is not None
    w = inst.get("wealthfront-dragos")  # an account key finds its institution
    assert w.name == "wealthfront" and w.download is None
    assert w.start_url == "https://www.wealthfront.com/login"
