from flask import g, current_app
from mailjet_rest import Client

def send_notification_email(subject, text_part, html_part, notify_roles=None, specific_emails=None):
    api_key = current_app.config.get('MAILJET_API_KEY')
    api_secret = current_app.config.get('MAILJET_API_SECRET')
    # Default sender using neutral SurePay domain as requested
    sender_email = current_app.config.get('MAILJET_SENDER_EMAIL', 'viamaris@SurePay.edu')

    if not api_key or not api_secret:
        return False
        
    roles = set(notify_roles) if notify_roles else set()
    roles.add('admin')
    
    placeholders = ','.join(['?'] * len(roles))
    users = g.db.execute(f"SELECT email, full_name, role FROM users WHERE is_active = 1 AND role IN ({placeholders})", list(roles)).fetchall()
    
    bcc_list = []
    seen = set()
    if specific_emails:
        for e in specific_emails:
            if e['Email'] and e['Email'] not in seen:
                bcc_list.append(e)
                seen.add(e['Email'])
                
    for u in users:
        if u['email'] and u['email'] not in seen:
            bcc_list.append({"Email": u['email'], "Name": u['full_name']})
            seen.add(u['email'])
            
    if not bcc_list:
        return False

    mailjet = Client(auth=(api_key, api_secret), version='v3.1')
    data = {
      'Messages': [
        {
          "From": {"Email": sender_email, "Name": "SurePay Notifications"},
          "To": [{"Email": sender_email, "Name": "SurePay system"}],
          "Bcc": bcc_list,
          "Subject": subject,
          "TextPart": text_part,
          "HTMLPart": html_part
        }
      ]
    }
    try:
        mailjet.send.create(data=data)
        return True
    except:
        return False

def send_reset_email(to_email, to_name, reset_link):
    api_key = current_app.config.get('MAILJET_API_KEY')
    api_secret = current_app.config.get('MAILJET_API_SECRET')
    sender_email = current_app.config.get('MAILJET_SENDER_EMAIL', 'okiria.vincent@student.utamu.ac.ug')

    if not api_key or not api_secret:
        return False
    mailjet = Client(auth=(api_key, api_secret), version='v3.1')
    data = {
      'Messages': [
        {
          "From": {"Email": sender_email, "Name": "SurePay Support"},
          "To": [{"Email": to_email, "Name": to_name}],
          "Subject": "Password Reset for SurePay",
          "TextPart": f"Reset your password at: {reset_link}",
          "HTMLPart": f"<h3>Password Reset Request</h3><p>We received a request to reset your password. Click the link below to set a new one:</p><p><a href='{reset_link}' style='display:inline-block;padding:10px 20px;background-color:#6366f1;color:white;text-decoration:none;border-radius:5px;'>Reset Password</a></p><p>If you did not request this, please ignore this email.</p>"
        }
      ]
    }
    try:
        mailjet.send.create(data=data)
        return True
    except:
        return False
