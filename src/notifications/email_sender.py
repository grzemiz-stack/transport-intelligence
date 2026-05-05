"""EmailSender — wysylanie emaili alertowych, raportowych i digest przez SMTP."""

import logging
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import aiosmtplib
from jinja2 import Environment, FileSystemLoader

from src.config import settings

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"

_jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=True,
)


def _render(template_name: str, **ctx) -> str:
    """Renderuje szablon Jinja2 z kontekstem."""
    ctx.setdefault("dashboard_url", settings.dashboard_url)
    ctx.setdefault("year", datetime.utcnow().year)
    ctx.setdefault("recipient_email", "")
    tpl = _jinja_env.get_template(template_name)
    return tpl.render(**ctx)


def _strip_html(html: str) -> str:
    """Prosty fallback plaintext — usuwa tagi HTML."""
    import re
    text = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


class EmailSender:
    """Wysyla emaile przez async SMTP (aiosmtplib)."""

    def __init__(self):
        self.host = settings.smtp_host
        self.port = settings.smtp_port
        self.user = settings.smtp_user
        self.password = settings.smtp_password
        self.from_addr = settings.smtp_from
        self.enabled = settings.smtp_enabled

    async def _send(self, msg: MIMEMultipart, recipients: list[str]) -> bool:
        """Wysyla gotowy email MIME. Zwraca True jesli sukces."""
        if not self.enabled:
            logger.info(
                "Email disabled, would send to: %s — subject: %s",
                ", ".join(recipients), msg["Subject"],
            )
            return True

        try:
            await aiosmtplib.send(
                msg,
                hostname=self.host,
                port=self.port,
                username=self.user,
                password=self.password,
                start_tls=True,
            )
            logger.info("Email sent to %s — subject: %s", ", ".join(recipients), msg["Subject"])
            return True
        except Exception as e:
            logger.error("Failed to send email to %s: %s", ", ".join(recipients), e)
            return False

    def _build_message(
        self, subject: str, html: str, recipients: list[str],
    ) -> MIMEMultipart:
        """Buduje MIME multipart z HTML + plaintext fallback."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.from_addr
        msg["To"] = ", ".join(recipients)

        plain = _strip_html(html)
        msg.attach(MIMEText(plain, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))
        return msg

    # ── Public API ────────────────────────────────────────────────────────

    async def send_alert_email(self, alert: dict, recipients: list[str]) -> bool:
        """Wysyla email alertowy do listy odbiorcow."""
        severity = (alert.get("severity") or "medium").lower()
        title = alert.get("title", "Alert")
        subject = f"[TI ALERT] {severity.upper()}: {title}"

        html = _render(
            "alert_email.html",
            severity=severity,
            title=title,
            description=alert.get("description", ""),
            alert_type=alert.get("alert_type", ""),
            country_codes=alert.get("country_codes") or [],
            region=alert.get("region"),
            triggered_at=alert.get("triggered_at", ""),
            related_events=alert.get("related_events") or [],
            alert_id=str(alert.get("id", "")),
            recipient_email=recipients[0] if recipients else "",
        )

        msg = self._build_message(subject, html, recipients)
        return await self._send(msg, recipients)

    async def send_report_email(
        self, report: dict, recipients: list[str], pdf_path: str | None = None,
    ) -> bool:
        """Wysyla email z informacja o nowym raporcie, opcjonalnie z PDF."""
        title = report.get("title", "Report")
        subject = f"[TI Report] {title}"

        html = _render(
            "report_email.html",
            title=title,
            report_type=report.get("report_type", ""),
            period_start=report.get("period_start", ""),
            period_end=report.get("period_end", ""),
            countries=report.get("countries") or [],
            total_events=report.get("total_events", 0),
            summary=report.get("summary", ""),
            report_id=str(report.get("id", "")),
            has_attachment=pdf_path is not None,
            recipient_email=recipients[0] if recipients else "",
        )

        msg = self._build_message(subject, html, recipients)

        # Dolacz PDF jesli podano sciezke
        if pdf_path:
            pdf_file = Path(pdf_path)
            if pdf_file.exists():
                with open(pdf_file, "rb") as f:
                    attachment = MIMEApplication(f.read(), _subtype="pdf")
                    attachment.add_header(
                        "Content-Disposition", "attachment",
                        filename=pdf_file.name,
                    )
                    msg.attach(attachment)

        return await self._send(msg, recipients)

    async def send_digest_email(
        self, events_summary: dict, recipients: list[str],
    ) -> bool:
        """Wysyla dzienny/tygodniowy digest zdarzen."""
        subject = f"[TI Digest] {events_summary.get('period_start', 'Daily')} — {events_summary.get('period_end', 'Summary')}"

        html = _render(
            "digest_email.html",
            total_events=events_summary.get("total_events", 0),
            critical_count=events_summary.get("critical_count", 0),
            alerts_count=events_summary.get("alerts_count", 0),
            top_events=events_summary.get("top_events") or [],
            new_hotspots=events_summary.get("new_hotspots") or [],
            companies_at_risk=events_summary.get("companies_at_risk") or [],
            per_country=events_summary.get("per_country") or {},
            period_start=events_summary.get("period_start", ""),
            period_end=events_summary.get("period_end", ""),
            recipient_email=recipients[0] if recipients else "",
        )

        msg = self._build_message(subject, html, recipients)
        return await self._send(msg, recipients)

    async def send_raw_email(
        self,
        subject: str,
        body_text: str,
        recipients: list[str] | None = None,
    ) -> bool:
        """Wysyla prosty email tekstowy (bez szablonu HTML).

        Jesli recipients nie podane, wysyla do smtp_user (self-notification).
        """
        if not recipients:
            recipients = [self.user] if self.user else []
        if not recipients:
            logger.warning("No recipients for raw email — skipping")
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.from_addr
        msg["To"] = ", ".join(recipients)
        msg.attach(MIMEText(body_text, "plain", "utf-8"))

        return await self._send(msg, recipients)
