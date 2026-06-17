from datetime import datetime

def timeago(dt_str):
    if not dt_str:
        return ''
    try:
        dt = datetime.strptime(str(dt_str), '%Y-%m-%d %H:%M:%S')
        now = datetime.utcnow()
        diff = now - dt
        
        if diff.days > 365:
            return f"{diff.days // 365}y ago"
        elif diff.days > 30:
            return f"{diff.days // 30}mo ago"
        elif diff.days > 0:
            return f"{diff.days}d ago"
        elif diff.seconds > 3600:
            return f"{diff.seconds // 3600}h ago"
        elif diff.seconds > 60:
            return f"{diff.seconds // 60}m ago"
        else:
            return "just now"
    except Exception:
        return str(dt_str)

def nl2br(value):
    if not value:
        return ''
    from markupsafe import Markup, escape
    return Markup(escape(value).replace('\n', '<br>\n'))

def register_filters(app):
    app.template_filter('timeago')(timeago)
    app.template_filter('nl2br')(nl2br)
