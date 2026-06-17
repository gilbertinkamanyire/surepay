from flask import render_template, request, redirect, url_for, session, flash, g, abort
from helpers import login_required, send_notification_email

def register_discussions(app):


    @app.route('/courses/<int:course_id>/discussions')
    @login_required
    def discussions_list(course_id):
        course = g.db.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()
        if not course:
            abort(404)

        discussions = g.db.execute('''
            SELECT d.*, u.full_name as author_name,
                   (SELECT COUNT(*) FROM replies WHERE discussion_id = d.id) as reply_count
            FROM discussions d JOIN users u ON d.user_id = u.id
            WHERE d.course_id = ?
            ORDER BY d.created_at DESC
        ''', (course_id,)).fetchall()

        return render_template('discussions/list.html',
                             course=course,
                             discussions=discussions)


    @app.route('/courses/<int:course_id>/discussions/<int:discussion_id>')
    @login_required
    def view_discussion(course_id, discussion_id):
        discussion = g.db.execute('''
            SELECT d.*, u.full_name as author_name
            FROM discussions d JOIN users u ON d.user_id = u.id
            WHERE d.id = ? AND d.course_id = ?
        ''', (discussion_id, course_id)).fetchone()

        if not discussion:
            abort(404)

        course = g.db.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()

        replies = g.db.execute('''
            SELECT r.*, u.full_name as author_name, u.role as author_role
            FROM replies r JOIN users u ON r.user_id = u.id
            WHERE r.discussion_id = ?
            ORDER BY r.created_at ASC
        ''', (discussion_id,)).fetchall()

        return render_template('discussions/thread.html',
                             course=course,
                             discussion=discussion,
                             replies=replies)


    @app.route('/courses/<int:course_id>/discussions/create', methods=['GET', 'POST'])
    @login_required
    def create_discussion(course_id):
        course = g.db.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()
        if not course:
            abort(404)

        if request.method == 'POST':
            title = request.form.get('title', '').strip()
            content = request.form.get('content', '').strip()

            if title and content:
                g.db.execute(
                    'INSERT INTO discussions (course_id, user_id, title, content) VALUES (?, ?, ?, ?)',
                    (course_id, session['user_id'], title, content)
                )
                g.db.commit()
                
                # Notify lecturer
                lecturer = g.db.execute('''
                    SELECT u.email, u.full_name FROM courses c 
                    JOIN users u ON c.admin_id = u.id 
                    WHERE c.id = ?
                ''', (course_id,)).fetchone()
                
                if lecturer:
                    send_notification_email(
                        subject=f"New Discussion in {course['title']}: {title}",
                        text_part=f"A student ({session.get('full_name')}) started a new discussion: {title}",
                        html_part=f"<h3>New Discussion</h3><p><b>{session.get('full_name')}</b> started a discussion in <b>{course['title']}</b>:</p><p><i>{title}</i></p><p>{content}</p>",
                        specific_emails=[{"Email": lecturer['email'], "Name": lecturer['full_name']}]
                    )
                
                flash('Discussion created!', 'success')
                return redirect(url_for('discussions_list', course_id=course_id))
            else:
                flash('Title and content are required.', 'danger')

        return render_template('discussions/create.html', course=course)


    @app.route('/courses/<int:course_id>/discussions/<int:discussion_id>/reply', methods=['POST'])
    @login_required
    def reply_discussion(course_id, discussion_id):
        content = request.form.get('content', '').strip()

        if content:
            g.db.execute(
                'INSERT INTO replies (discussion_id, user_id, content) VALUES (?, ?, ?)',
                (discussion_id, session['user_id'], content)
            )
            g.db.commit()
            
            # Notify lecturer and discussion author
            course = g.db.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()
            discussion = g.db.execute('SELECT * FROM discussions WHERE id = ?', (discussion_id,)).fetchone()
            author = g.db.execute('SELECT email, full_name FROM users WHERE id = ?', (discussion['user_id'],)).fetchone()
            lecturer = g.db.execute('SELECT email, full_name FROM users WHERE id = ?', (course['admin_id'],)).fetchone()
            
            notify_emails = []
            seen = {session.get('email')} # Don't notify the person who just replied
            
            if author and author['email'] not in seen:
                notify_emails.append({"Email": author['email'], "Name": author['full_name']})
                seen.add(author['email'])
            if lecturer and lecturer['email'] not in seen:
                notify_emails.append({"Email": lecturer['email'], "Name": lecturer['full_name']})
                seen.add(lecturer['email'])
                
            if notify_emails:
                send_notification_email(
                    subject=f"New Reply in {discussion['title']}",
                    text_part=f"{session.get('full_name')} replied to the discussion: {content[:100]}...",
                    html_part=f"<h3>New Reply</h3><p><b>{session.get('full_name')}</b> replied to <b>{discussion['title']}</b>:</p><p>{content}</p>",
                    specific_emails=notify_emails
                )
                
            flash('Reply posted!', 'success')
        else:
            flash('Reply cannot be empty.', 'danger')

        return redirect(url_for('view_discussion', course_id=course_id, discussion_id=discussion_id))


