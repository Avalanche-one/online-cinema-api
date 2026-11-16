from decimal import Decimal
from email import message_from_string
from typing import ClassVar
from unittest.mock import AsyncMock

import aiosmtplib
import pytest

from online_cinema_api.exceptions import BaseEmailError
from online_cinema_api.notifications import emails as emails_module
from online_cinema_api.notifications.emails import EmailSender
from online_cinema_api.notifications.interfaces import EmailSenderInterface


@pytest.fixture
def template_dir(tmp_path):
    templates = {
        "activation.html": "ACT {{ email }} {{ activation_link }}",
        "activation_complete.html": "DONE {{ email }} {{ login_link }}",
        "reset.html": "RESET {{ email }} {{ reset_link }}",
        "reset_complete.html": "RESETDONE {{ email }} {{ login_link }}",
        "payment_confirmation.html": (
            "ORDER {{ order_id }} {{ amount }} {{ movies | join(', ') }} {{ email }}"
        ),
    }
    for name, content in templates.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    return tmp_path


@pytest.fixture
def sender(template_dir) -> EmailSender:
    return EmailSender(
        hostname="smtp.test",
        port=2525,
        email="noreply@cinema.test",
        password="pw",
        use_tls=True,
        template_dir=str(template_dir),
        activation_email_template_name="activation.html",
        activation_complete_email_template_name="activation_complete.html",
        password_email_template_name="reset.html",
        password_complete_email_template_name="reset_complete.html",
        payment_confirmation_email_template_name="payment_confirmation.html",
    )


@pytest.fixture
def smtp(monkeypatch):
    """Replace aiosmtplib.SMTP. Failures can be simulated through the class attributes."""

    class FakeSMTP:
        instances: ClassVar[list[FakeSMTP]] = []
        fail_on: ClassVar[str | None] = None
        error: ClassVar[Exception | None] = None

        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.login = AsyncMock()
            self.sendmail = AsyncMock()
            if FakeSMTP.fail_on in ("login", "sendmail"):
                getattr(self, FakeSMTP.fail_on).side_effect = FakeSMTP.error
            FakeSMTP.instances.append(self)

        async def __aenter__(self):
            if FakeSMTP.fail_on == "connect":
                raise FakeSMTP.error
            return self

        async def __aexit__(self, *exc_info):
            return False

    monkeypatch.setattr(emails_module.aiosmtplib, "SMTP", FakeSMTP)
    return FakeSMTP


def _parse_sent(smtp_cls):
    assert len(smtp_cls.instances) == 1
    client = smtp_cls.instances[0]
    from_addr, recipients, raw = client.sendmail.await_args.args
    message = message_from_string(raw)
    body = message.get_payload(0).get_payload(decode=True).decode()
    return client, from_addr, recipients, message, body


def test_sender_implements_interface():
    assert issubclass(EmailSender, EmailSenderInterface)
    with pytest.raises(TypeError):
        EmailSenderInterface()


CASES = [
    (
        "send_activation_email",
        ("u@x.com", "http://site/activate"),
        "Account Activation",
        ["ACT", "u@x.com", "http://site/activate"],
    ),
    (
        "send_activation_complete_email",
        ("u@x.com", "http://site/login"),
        "Account Activated Successfully",
        ["DONE", "u@x.com", "http://site/login"],
    ),
    (
        "send_password_reset_email",
        ("u@x.com", "http://site/reset"),
        "Password Reset Request",
        ["RESET", "u@x.com", "http://site/reset"],
    ),
    (
        "send_password_reset_complete_email",
        ("u@x.com", "http://site/login"),
        "Your Password Has Been Successfully Reset",
        ["RESETDONE", "u@x.com", "http://site/login"],
    ),
    (
        "send_payment_confirmation_email",
        ("u@x.com", 7, Decimal("19.98"), ["Alien", "Heat"]),
        "Payment Confirmation for Order #7",
        ["ORDER 7", "19.98", "Alien, Heat", "u@x.com"],
    ),
]


@pytest.mark.parametrize(("method", "args", "subject", "fragments"), CASES)
async def test_send_methods_render_template_and_send(
    sender, smtp, method, args, subject, fragments
):
    await getattr(sender, method)(*args)

    _client, from_addr, recipients, message, body = _parse_sent(smtp)
    assert from_addr == "noreply@cinema.test"
    assert recipients == ["u@x.com"]
    assert message["From"] == "noreply@cinema.test"
    assert message["To"] == "u@x.com"
    assert message["Subject"] == subject
    assert message.get_content_subtype() == "mixed"
    assert message.get_payload(0).get_content_type() == "text/html"
    for fragment in fragments:
        assert fragment in body


async def test_smtp_connection_parameters_and_login(sender, smtp):
    await sender.send_activation_email("u@x.com", "http://site/a")

    client = smtp.instances[0]
    assert client.kwargs == {"hostname": "smtp.test", "port": 2525, "start_tls": True}
    client.login.assert_awaited_once_with("noreply@cinema.test", "pw")


async def test_html_templates_are_autoescaped(sender, smtp):
    await sender.send_activation_email("u@x.com", "<script>alert(1)</script>")

    *_, body = _parse_sent(smtp)
    assert "<script>" not in body
    assert "&lt;script&gt;" in body


async def test_payment_template_name_has_default(template_dir, smtp):
    sender = EmailSender(
        hostname="h",
        port=25,
        email="e@x.com",
        password="p",
        use_tls=False,
        template_dir=str(template_dir),
        activation_email_template_name="activation.html",
        activation_complete_email_template_name="activation_complete.html",
        password_email_template_name="reset.html",
        password_complete_email_template_name="reset_complete.html",
    )

    await sender.send_payment_confirmation_email("u@x.com", 1, Decimal(5), ["A"])

    *_, body = _parse_sent(smtp)
    assert "ORDER 1" in body


@pytest.mark.parametrize("stage", ["connect", "login", "sendmail"])
@pytest.mark.parametrize(
    "error", [aiosmtplib.SMTPException("smtp boom"), OSError("socket boom")]
)
async def test_smtp_failures_are_wrapped_in_base_email_error(
    sender, smtp, stage, error
):
    smtp.fail_on = stage
    smtp.error = error

    with pytest.raises(BaseEmailError, match="u@x.com"):
        await sender.send_activation_email("u@x.com", "http://site/a")


async def test_unexpected_errors_are_not_swallowed(sender, smtp):
    smtp.fail_on = "sendmail"
    smtp.error = RuntimeError("unexpected")

    with pytest.raises(RuntimeError):
        await sender.send_activation_email("u@x.com", "http://site/a")


async def test_missing_template_raises(sender, smtp, tmp_path):
    from jinja2 import TemplateNotFound

    broken = EmailSender(
        hostname="h",
        port=25,
        email="e@x.com",
        password="p",
        use_tls=False,
        template_dir=str(tmp_path / "does-not-exist"),
        activation_email_template_name="activation.html",
        activation_complete_email_template_name="x.html",
        password_email_template_name="y.html",
        password_complete_email_template_name="z.html",
    )

    with pytest.raises(TemplateNotFound):
        await broken.send_activation_email("u@x.com", "http://site/a")
    assert smtp.instances == []
