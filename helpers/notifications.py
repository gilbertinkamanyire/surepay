from flask import g
from helpers.email import send_notification_email

def create_notification(user_id, title, message, link=None):
    """Create an in-app notification and send an email alert."""
    g.db.execute(
        'INSERT INTO notifications (user_id, title, message, link) VALUES (?, ?, ?, ?)',
        (user_id, title, message, link)
    )
    g.db.commit()

    # Also send email notification
    user = g.db.execute('SELECT email, full_name FROM users WHERE id = ?', (user_id,)).fetchone()
    if user and user['email']:
        send_notification_email(
            subject=title,
            text_part=message,
            html_part=f"<h3>{title}</h3><p>{message}</p>",
            specific_emails=[{"Email": user['email'], "Name": user['full_name']}]
        )
