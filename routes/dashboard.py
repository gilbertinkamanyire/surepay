from flask import render_template, redirect, url_for, session, g
from helpers import login_required

def register_dashboard(app):

    @app.route('/dashboard')
    @login_required
    def dashboard():
        user_id = session['user_id']
        role = session['role']

        if role == 'employee':
            # Get enrolled categories with progress
            enrollments = g.db.execute('''
                SELECT e.*, c.title, c.description, c.category, c.image_url, u.full_name as admin_name,
                       (SELECT COUNT(*) FROM lessons WHERE category_id = c.id) as total_lessons
                FROM enrollments e
                JOIN categories c ON e.category_id = c.id
                JOIN users u ON c.admin_id = u.id
                WHERE e.employee_id = ?
                ORDER BY e.enrolled_at DESC
            ''', (user_id,)).fetchall()

            # Recent announcements
            announcements = g.db.execute('''
                SELECT a.*, u.full_name as author_name
                FROM announcements a JOIN users u ON a.user_id = u.id
                WHERE a.target_role IN ('all', 'employee')
                ORDER BY a.created_at DESC LIMIT 5
            ''').fetchall()

            # Upcoming assessments
            assessments = g.db.execute('''
                SELECT a.*, c.title as category_title
                FROM assessments a
                JOIN categories c ON a.category_id = c.id
                JOIN enrollments e ON e.category_id = c.id
                WHERE e.employee_id = ?
                AND a.id NOT IN (SELECT assessment_id FROM submissions WHERE employee_id = ?)
                ORDER BY a.created_at DESC LIMIT 5
            ''', (user_id, user_id)).fetchall()

            # Fetch earned badges
            badges = g.db.execute('''
                SELECT b.*, c.title as category_title
                FROM badges b
                JOIN categories c ON b.category_id = c.id
                WHERE b.user_id = ?
                ORDER BY b.awarded_at DESC
            ''', (user_id,)).fetchall()

            # Overall stats
            total_enrolled = len(enrollments)
            total_completed = sum(1 for e in enrollments if e['progress'] >= 100)

            # Leaderboard & Streak
            user_info = g.db.execute('SELECT current_streak FROM users WHERE id = ?', (user_id,)).fetchone()
            streak = user_info['current_streak'] if user_info and user_info['current_streak'] else 0

            # Calculate global leaderboard points
            # Formula: SUM(participation_points) + 50*(golden) + 30*(silver) + 10*(bronze) + 5*(others)
            leaderboard = g.db.execute('''
                SELECT u.id, u.full_name, u.profile_pic_url,
                       COALESCE((SELECT SUM(participation_points) FROM enrollments WHERE employee_id = u.id), 0) +
                       COALESCE((SELECT SUM(
                           CASE 
                               WHEN badge_type = 'golden' THEN 50
                               WHEN badge_type = 'silver' THEN 30
                               WHEN badge_type = 'bronze' THEN 10
                               ELSE 5
                           END) FROM badges WHERE user_id = u.id), 0) as total_points
                FROM users u
                WHERE u.role = 'employee'
                ORDER BY total_points DESC, u.full_name ASC
                LIMIT 10
            ''').fetchall()

            return render_template('dashboard/employee.html',
                                 enrollments=enrollments,
                                 announcements=announcements,
                                 assessments=assessments,
                                 badges=badges,
                                 total_enrolled=total_enrolled,
                                 total_completed=total_completed,
                                 streak=streak,
                                 leaderboard=leaderboard)

        else:  # admin
            stats = {
                'total_users': g.db.execute('SELECT COUNT(*) FROM users').fetchone()[0],
                'total_employees': g.db.execute("SELECT COUNT(*) FROM users WHERE role='employee'").fetchone()[0],
                'total_categories': g.db.execute('SELECT COUNT(*) FROM categories').fetchone()[0],
                'published_categories': g.db.execute('SELECT COUNT(*) FROM categories WHERE is_published=1').fetchone()[0],
                'total_enrollments': g.db.execute('SELECT COUNT(*) FROM enrollments').fetchone()[0],
                'total_discussions': g.db.execute('SELECT COUNT(*) FROM discussions').fetchone()[0],
                'total_submissions': g.db.execute('SELECT COUNT(*) FROM submissions').fetchone()[0],
            }

            recent_users = g.db.execute('''
                SELECT * FROM users ORDER BY created_at DESC LIMIT 10
            ''').fetchall()
            
            # Get admin's categories
            categories = g.db.execute('''
                SELECT c.*,
                       (SELECT COUNT(*) FROM enrollments WHERE category_id = c.id) as student_count,
                       (SELECT COUNT(*) FROM lessons WHERE category_id = c.id) as lesson_count,
                       (SELECT COUNT(*) FROM discussions WHERE category_id = c.id) as discussion_count
                FROM categories c WHERE c.admin_id = ?
                ORDER BY c.created_at DESC
            ''', (user_id,)).fetchall()

            # Recent discussions across all categories
            recent_discussions = g.db.execute('''
                SELECT d.*, c.title as category_title, u.full_name as author_name,
                       (SELECT COUNT(*) FROM replies WHERE discussion_id = d.id) as reply_count
                FROM discussions d
                JOIN categories c ON d.category_id = c.id
                JOIN users u ON d.user_id = u.id
                WHERE c.admin_id = ?
                ORDER BY d.created_at DESC LIMIT 5
            ''', (user_id,)).fetchall()

            return render_template('dashboard/admin.html',
                                 stats=stats,
                                 recent_users=recent_users,
                                 categories=categories,
                                 recent_discussions=recent_discussions)
