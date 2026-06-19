from flask import render_template, redirect, url_for, session, flash, g
from helpers import login_required

def register_grades(app):

    @app.route('/grades')
    @login_required
    def employee_grades():
        if session['role'] != 'employee':
            flash('Only employees can view their grades here.', 'info')
            return redirect(url_for('dashboard'))

        user_id = session['user_id']

        # Get enrollment performance
        enrollments = g.db.execute('''
            SELECT e.*, c.title as category_title,
                   (SELECT COUNT(*) FROM lessons WHERE category_id = c.id) as total_lessons,
                   (SELECT COUNT(DISTINCT lesson_id) FROM attendance WHERE user_id = ? AND category_id = c.id AND activity_type = 'view') as lessons_viewed,
                   (SELECT COUNT(*) FROM attendance WHERE user_id = ? AND category_id = c.id AND activity_type = 'download') as files_downloaded,
                   e.participation_points
            FROM enrollments e
            JOIN categories c ON e.category_id = c.id
            WHERE e.employee_id = ?
        ''', (user_id, user_id, user_id)).fetchall()

        # Get assessment scores
        assessments = g.db.execute('''
            SELECT sub.*, a.title, sub.max_score as quiz_max_score, c.title as category_title
            FROM submissions sub
            JOIN assessments a ON sub.assessment_id = a.id
            JOIN categories c ON a.category_id = c.id
            WHERE sub.employee_id = ?
            ORDER BY sub.submitted_at DESC
        ''', (user_id,)).fetchall()

        return render_template('grades/employee.html', 
                             enrollments=enrollments, 
                             assessments=assessments)

    @app.route('/notifications')
    @login_required
    def notifications():
        notifications = g.db.execute('''
            SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC
        ''', (session['user_id'],)).fetchall()
        
        # Mark all as read
        g.db.execute('UPDATE notifications SET is_read = 1 WHERE user_id = ?', (session['user_id'],))
        g.db.commit()
        
        return render_template('notifications.html', notifications=notifications)
