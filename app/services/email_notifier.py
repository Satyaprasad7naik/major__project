"""
Email Notifier Service for InsightOS.
Sends proactive auto-generated insights notifications via SMTP or fallback logging.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Any, Optional
from app.core.config import settings
from app.core.logger import logger


def format_insight_email_html(insights: List[Dict[str, Any]], headline: str) -> str:
    """Format proactive insights into an HTML email body."""
    cards_html = ""
    for ins in insights:
        sev = (ins.get("severity") or "MEDIUM").upper()
        badge_color = "#e53e3e" if sev in ("HIGH", "CRITICAL") else ("#dd6b20" if sev == "MEDIUM" else "#3182ce")
        badge_bg = "#fff5f5" if sev in ("HIGH", "CRITICAL") else ("#fffaf0" if sev == "MEDIUM" else "#ebf8ff")
        
        cards_html += f"""
        <div style="border-left: 4px solid {badge_color}; background-color: {badge_bg}; padding: 12px 16px; margin-bottom: 12px; border-radius: 4px;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <h3 style="margin: 0; font-size: 16px; color: #1a202c;">{ins.get('title', 'Insight Alert')}</h3>
                <span style="font-size: 11px; font-weight: bold; padding: 2px 8px; border-radius: 12px; color: white; background-color: {badge_color};">
                    {sev}
                </span>
            </div>
            <p style="margin: 6px 0; font-size: 14px; color: #4a5568;">{ins.get('description', '')}</p>
            {f'<p style="margin: 4px 0 0 0; font-size: 12px; color: #718096;"><strong>Product:</strong> {ins.get("product_name")}</p>' if ins.get('product_name') else ''}
        </div>
        """

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>InsightOS Proactive Alert</title>
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f7fafc; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background: white; padding: 24px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            <div style="border-bottom: 2px solid #e2e8f0; padding-bottom: 16px; margin-bottom: 20px;">
                <h1 style="color: #2b6cb0; margin: 0; font-size: 22px;">📊 InsightOS Proactive Intelligence</h1>
                <p style="margin: 8px 0 0 0; font-size: 16px; font-weight: bold; color: #2d3748;">{headline}</p>
            </div>
            
            <div style="margin-bottom: 20px;">
                {cards_html}
            </div>

            <div style="border-top: 1px solid #e2e8f0; padding-top: 16px; font-size: 12px; color: #a0aec0; text-align: center;">
                Automated notification sent by InsightOS Proactive Engine. No response needed.
            </div>
        </div>
    </body>
    </html>
    """
    return html


async def send_email_insight_alert(
    insights: List[Dict[str, Any]],
    headline: str,
    sender_email: Optional[str] = None,
    sender_password: Optional[str] = None,
    receiver_emails: Optional[str] = None,
    smtp_server: Optional[str] = None,
    smtp_port: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Send email notification for newly generated proactive insights.
    Uses provided credentials or falls back to environment/settings.
    Returns structured result with success status and detailed diagnostics.
    """
    import os
    if not insights:
        return {"success": False, "message": "No insights to send."}

    # Resolve settings
    smtp_host = smtp_server or os.getenv("SMTP_SERVER") or os.getenv("SMTP_HOST") or getattr(settings, "SMTP_SERVER", None) or getattr(settings, "SMTP_HOST", "smtp.gmail.com")
    smtp_port_val = smtp_port or os.getenv("SMTP_PORT") or getattr(settings, "SMTP_PORT", 587)
    try:
        smtp_port_num = int(smtp_port_val)
    except (ValueError, TypeError):
        smtp_port_num = 587

    smtp_user = sender_email or os.getenv("SMTP_EMAIL") or os.getenv("SMTP_USER") or getattr(settings, "SMTP_EMAIL", None)
    smtp_pass = sender_password or os.getenv("SMTP_PASSWORD") or getattr(settings, "SMTP_PASSWORD", None)
    recipients_str = receiver_emails or os.getenv("NOTIFICATION_EMAIL") or os.getenv("ALERT_EMAIL_RECIPIENTS") or getattr(settings, "NOTIFICATION_EMAIL", "")

    # Clean and split recipients
    recipients = [r.strip() for r in str(recipients_str).split(",") if r.strip() and "@" in r]

    is_placeholder = bool(
        not smtp_user or "your_email" in smtp_user.lower() or not smtp_pass or "your_app_password" in smtp_pass.lower() or "app_specific_secret_pwd" in smtp_pass.lower()
    )

    if not smtp_user:
        return {
            "success": False,
            "message": "Sender email is not configured.",
            "error_type": "MISSING_SENDER"
        }

    if not recipients:
        return {
            "success": False,
            "message": "Receiver email is not configured.",
            "error_type": "MISSING_RECEIVER"
        }

    if is_placeholder:
        logger.warning(
            f"SMTP not fully configured or using placeholder credentials ({smtp_user}). "
            f"Proactive email alert for '{headline}' was logged to fallback."
        )
        return {
            "success": False,
            "message": "Please enter a valid Sender App Password to dispatch real emails.",
            "error_type": "PLACEHOLDER_PASSWORD"
        }

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"InsightOS Alert – {headline}"
        msg["From"] = smtp_user
        msg["To"] = ", ".join(recipients)

        html_body = format_insight_email_html(insights, headline)
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(smtp_host, smtp_port_num, timeout=12) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            if smtp_user and smtp_pass:
                server.login(smtp_user, smtp_pass)
            server.sendmail(msg["From"], recipients, msg.as_string())

        logger.info(f"Email sent successfully to {', '.join(recipients)}")
        return {
            "success": True,
            "message": f"Test email sent successfully to {', '.join(recipients)}",
            "recipients": recipients
        }
    except smtplib.SMTPAuthenticationError as auth_err:
        err_msg = str(auth_err)
        logger.error(f"SMTP Authentication Error: {err_msg}")
        hint = ""
        if "gmail.com" in (smtp_host or "").lower() or "535" in err_msg or "5.7.8" in err_msg:
            hint = " For Gmail, Google requires a 16-character App Password (not your normal Gmail password). Generate one at: https://myaccount.google.com/apppasswords"
        return {
            "success": False,
            "message": f"SMTP Authentication failed (Invalid username/password).{hint}",
            "error_details": err_msg,
            "error_type": "AUTH_ERROR"
        }
    except smtplib.SMTPConnectError as conn_err:
        logger.error(f"SMTP Connect Error: {conn_err}")
        return {
            "success": False,
            "message": f"Could not connect to SMTP server {smtp_host}:{smtp_port_num}. Check your host and port.",
            "error_details": str(conn_err),
            "error_type": "CONNECT_ERROR"
        }
    except Exception as exc:
        logger.error(f"Failed to send email: {exc}")
        return {
            "success": False,
            "message": f"Failed to send email: {str(exc)}",
            "error_details": str(exc),
            "error_type": "GENERAL_ERROR"
        }


def get_smtp_status() -> Dict[str, Any]:
    """Return current SMTP configuration status and diagnostics (safe, hides password)."""
    import os
    smtp_host = os.getenv("SMTP_SERVER") or os.getenv("SMTP_HOST") or getattr(settings, "SMTP_SERVER", None) or getattr(settings, "SMTP_HOST", None)
    smtp_port = os.getenv("SMTP_PORT") or getattr(settings, "SMTP_PORT", 587)
    smtp_user = os.getenv("SMTP_EMAIL") or os.getenv("SMTP_USER") or getattr(settings, "SMTP_EMAIL", None) or getattr(settings, "SMTP_USER", None)
    smtp_pass = os.getenv("SMTP_PASSWORD") or getattr(settings, "SMTP_PASSWORD", None)
    recipients_str = os.getenv("NOTIFICATION_EMAIL") or os.getenv("ALERT_EMAIL_RECIPIENTS") or getattr(settings, "NOTIFICATION_EMAIL", "")

    recipients = [r.strip() for r in (recipients_str or "").split(",") if r.strip() and "@" in r]
    is_placeholder = bool(
        not smtp_user or "your_email" in smtp_user.lower() or not smtp_pass or "your_app_password" in smtp_pass.lower() or "app_specific_secret_pwd" in smtp_pass.lower()
    )
    is_ready = bool(smtp_host and smtp_user and smtp_pass and not is_placeholder and recipients)

    return {
        "is_configured": is_ready,
        "smtp_server": smtp_host or "smtp.gmail.com",
        "smtp_port": int(smtp_port) if smtp_port else 587,
        "sender_email": smtp_user or "Not configured",
        "has_password": bool(smtp_pass and not is_placeholder),
        "recipient_count": len(recipients),
        "recipients": recipients,
        "mode": "Active SMTP Dispatch" if is_ready else "Safe Fallback (Console / System Log)"
    }


async def test_email_connection(
    sender_email: Optional[str] = None,
    sender_password: Optional[str] = None,
    receiver_emails: Optional[str] = None,
    smtp_server: Optional[str] = None,
    smtp_port: Optional[int] = None,
    save_config: bool = True
) -> Dict[str, Any]:
    """Test SMTP connection and optionally save working credentials."""
    # If credentials were provided in the test call and save_config is requested, persist them
    if (sender_email or receiver_emails or sender_password) and save_config:
        update_email_config(
            sender_email=sender_email,
            sender_password=sender_password,
            receiver_emails=receiver_emails,
            smtp_server=smtp_server,
            smtp_port=smtp_port
        )

    sample_insights = [
        {
            "title": "System Test Alert - Inventory Health",
            "description": "This is a live test notification verifying your InsightOS email alert configuration.",
            "severity": "HIGH",
            "product_name": "Retail Live Sales Monitor"
        }
    ]

    result = await send_email_insight_alert(
        insights=sample_insights,
        headline="InsightOS Email Notification Test",
        sender_email=sender_email,
        sender_password=sender_password,
        receiver_emails=receiver_emails,
        smtp_server=smtp_server,
        smtp_port=smtp_port
    )

    status = get_smtp_status()
    return {
        "status": "success" if result.get("success") else "fallback_logged",
        "smtp_configured": status["is_configured"],
        "dispatched": result.get("success", False),
        "message": result.get("message", ""),
        "error_type": result.get("error_type"),
        "error_details": result.get("error_details"),
        "details": status
    }


def update_email_config(
    sender_email: Optional[str] = None,
    sender_password: Optional[str] = None,
    receiver_emails: Optional[str] = None,
    smtp_server: Optional[str] = None,
    smtp_port: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Update SMTP and recipient settings at runtime and persist into .env file.
    Automatically infers SMTP host for popular email providers (Gmail, Outlook, Yahoo) if not set.
    """
    import os
    import re

    # Infer default SMTP host if not provided
    if sender_email and not smtp_server:
        clean_email = sender_email.strip().lower()
        if "@gmail.com" in clean_email or "@googlemail.com" in clean_email:
            smtp_server = "smtp.gmail.com"
            smtp_port = smtp_port or 587
        elif "@outlook.com" in clean_email or "@hotmail.com" in clean_email or "@live.com" in clean_email:
            smtp_server = "smtp.office365.com"
            smtp_port = smtp_port or 587
        elif "@yahoo.com" in clean_email:
            smtp_server = "smtp.mail.yahoo.com"
            smtp_port = smtp_port or 587

    # Update runtime environment
    updates = {}
    if sender_email is not None:
        val = sender_email.strip()
        os.environ["SMTP_EMAIL"] = val
        os.environ["SMTP_USER"] = val
        setattr(settings, "SMTP_EMAIL", val)
        updates["SMTP_EMAIL"] = val

    if sender_password is not None and sender_password.strip() != "":
        val = sender_password.strip()
        os.environ["SMTP_PASSWORD"] = val
        setattr(settings, "SMTP_PASSWORD", val)
        updates["SMTP_PASSWORD"] = val

    if receiver_emails is not None:
        val = receiver_emails.strip()
        os.environ["NOTIFICATION_EMAIL"] = val
        os.environ["ALERT_EMAIL_RECIPIENTS"] = val
        setattr(settings, "NOTIFICATION_EMAIL", val)
        updates["NOTIFICATION_EMAIL"] = val

    if smtp_server is not None:
        val = smtp_server.strip()
        os.environ["SMTP_SERVER"] = val
        os.environ["SMTP_HOST"] = val
        setattr(settings, "SMTP_SERVER", val)
        updates["SMTP_SERVER"] = val

    if smtp_port is not None:
        val = str(int(smtp_port))
        os.environ["SMTP_PORT"] = val
        setattr(settings, "SMTP_PORT", int(val))
        updates["SMTP_PORT"] = val

    # Persist into .env file
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    env_path = os.path.join(project_root, ".env")

    existing_lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            existing_lines = f.readlines()

    keys_to_update = set(updates.keys())
    updated_lines = []
    found_keys = set()

    for line in existing_lines:
        line_stripped = line.strip()
        matched_key = None
        for k in keys_to_update:
            if line_stripped.startswith(f"{k}=") or line_stripped.startswith(f'"{k}"=') or line_stripped.startswith(f"export {k}="):
                matched_key = k
                break
        if matched_key:
            updated_lines.append(f"{matched_key}={updates[matched_key]}\n")
            found_keys.add(matched_key)
        else:
            updated_lines.append(line)

    # Add missing keys to the end
    missing_keys = keys_to_update - found_keys
    if missing_keys:
        if updated_lines and not updated_lines[-1].endswith("\n"):
            updated_lines.append("\n")
        updated_lines.append("\n# Email Alerts (SMTP) Configuration\n")
        for k in sorted(missing_keys):
            updated_lines.append(f"{k}={updates[k]}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(updated_lines)

    logger.info(f"Email configuration updated successfully: {list(updates.keys())}")
    return {
        "status": "success",
        "message": "Email notification settings saved successfully",
        "current_status": get_smtp_status()
    }


