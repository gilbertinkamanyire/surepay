from flask import render_template, redirect, url_for, flash, session, g
from helpers import login_required

def register_unique(app):
    @app.route('/cognitive-mirror')
    @login_required
    def cognitive_mirror():
        user_id = session['user_id']
        db = g.db
        
        # 1. Analyze Pace (Lesson progress vs time)
        attendance = db.execute('''
            SELECT COUNT(*) as views, DATE(timestamp) as date 
            FROM attendance 
            WHERE user_id = ? 
            GROUP BY DATE(timestamp)
        ''', (user_id,)).fetchall()
        
        # 2. Analyze Focus Window (When do they study?)
        hours = db.execute('''
            SELECT STRFTIME('%H', timestamp) as hour, COUNT(*) as count 
            FROM attendance 
            WHERE user_id = ? 
            GROUP BY hour 
            ORDER BY count DESC 
            LIMIT 1
        ''', (user_id,)).fetchone()
        
        focus_window = "Not enough data yet"
        if hours:
            h = int(hours['hour'])
            if 5 <= h < 12: focus_window = "Early Bird 🌅"
            elif 12 <= h < 17: focus_window = "Afternoon Achiever ☀️"
            elif 17 <= h < 21: focus_window = "Evening Scholar 🌙"
            else: focus_window = "Night Owl 🦉"

        # 3. Analyze Struggle Points (Failed quiz questions or repeated lesson views)
        struggles = db.execute('''
            SELECT l.title, COUNT(a.id) as views 
            FROM attendance a
            JOIN lessons l ON a.lesson_id = l.id
            WHERE a.user_id = ? AND a.activity_type = 'view'
            GROUP BY a.lesson_id
            HAVING views > 3
            LIMIT 3
        ''', (user_id,)).fetchall()

        # 4. Strengths (Quick completions)
        strengths = db.execute('''
            SELECT l.title 
            FROM lesson_progress lp
            JOIN lessons l ON lp.lesson_id = l.id
            WHERE lp.employee_id = ? AND lp.completed = 1
            LIMIT 3
        ''', (user_id,)).fetchall()

        # 5. Competency mirror data
        competencies = db.execute('''
            SELECT c.id as course_id,
                   c.title as skill_name,
                   c.category,
                   e.progress,
                   COUNT(l.id) as total_lessons,
                   SUM(CASE WHEN lp.completed = 1 THEN 1 ELSE 0 END) as completed_lessons
            FROM enrollments e
            JOIN courses c ON e.course_id = c.id
            LEFT JOIN lessons l ON l.course_id = c.id
            LEFT JOIN lesson_progress lp ON lp.lesson_id = l.id AND lp.employee_id = ?
            WHERE e.employee_id = ?
            GROUP BY c.id, c.title, c.category, e.progress
            ORDER BY e.progress DESC, c.title
        ''', (user_id, user_id)).fetchall()

        competencies_mastered = []
        competencies_in_progress = []
        competencies_not_started = []
        for row in competencies:
            progress = float(row['progress'] or 0.0)
            skill = {
                'course_id': row['course_id'],
                'title': row['skill_name'],
                'category': row['category'] or 'General',
                'progress': round(progress, 0),
                'completed_lessons': int(row['completed_lessons'] or 0),
                'total_lessons': int(row['total_lessons'] or 0)
            }
            if progress >= 80:
                competencies_mastered.append(skill)
            elif progress > 0:
                competencies_in_progress.append(skill)
            else:
                competencies_not_started.append(skill)

        # 6. Collaboration stats for mirror
        collab_stats = db.execute('''
            SELECT COUNT(*) FROM synergy_matches 
            WHERE (user_a_id = ? OR user_b_id = ?)
        ''', (user_id, user_id)).fetchone()[0]

        # Get existing insights from DB
        stored_insights = db.execute('SELECT * FROM learning_insights WHERE user_id = ? ORDER BY created_at DESC', (user_id,)).fetchall()

        return render_template('unique/cognitive_mirror.html', 
                               focus_window=focus_window, 
                               struggles=struggles, 
                               strengths=strengths,
                               stored_insights=stored_insights,
                               competencies_mastered=competencies_mastered,
                               competencies_in_progress=competencies_in_progress,
                               competencies_not_started=competencies_not_started,
                               collab_count=collab_stats)

    @app.route('/synergy-connect')
    @login_required
    def synergy_connect():
        user_id = session['user_id']
        db = g.db
        
        # Collaborative data for Chart.js
        chart_data = db.execute('''
            SELECT c.title, COUNT(sm.id) as match_count
            FROM courses c
            JOIN synergy_matches sm ON c.id = sm.course_id
            GROUP BY c.id, c.title
            ORDER BY match_count DESC
            LIMIT 5
        ''').fetchall()
        
        labels = [row['title'] for row in chart_data]
        values = [row['match_count'] for row in chart_data]

        # Get my progress for comparison
        my_enrollments = db.execute('SELECT course_id, progress FROM enrollments WHERE employee_id = ?', (user_id,)).fetchall()
        my_progress_map = {e['course_id']: e['progress'] for e in my_enrollments}
        
        course_ids = [c['course_id'] for c in my_enrollments]
        
        peers = []
        if course_ids:
            placeholders = ', '.join(['?'] * len(course_ids))
            peers = db.execute(f'''
                SELECT DISTINCT u.id, u.full_name, u.profile_pic_url, c.title as course_title, e.progress, e.course_id
                FROM users u
                JOIN enrollments e ON u.id = e.employee_id
                JOIN courses c ON e.course_id = c.id
                WHERE e.course_id IN ({placeholders})
                AND u.id != ?
                ORDER BY RANDOM()
                LIMIT 5
            ''', (*course_ids, user_id)).fetchall()

        # Get current active matches
        active_matches = db.execute('''
            SELECT sm.*, u.full_name as peer_name, c.title as course_title
            FROM synergy_matches sm
            JOIN users u ON (CASE WHEN sm.user_a_id = ? THEN sm.user_b_id ELSE sm.user_a_id END) = u.id
            JOIN courses c ON sm.course_id = c.id
            WHERE (sm.user_a_id = ? OR sm.user_b_id = ?) AND sm.is_active = 1
        ''', (user_id, user_id, user_id)).fetchall()

        return render_template('unique/synergy_connect.html', 
                             peers=peers, 
                             my_progress=my_progress_map,
                             active_matches=active_matches,
                             chart_labels=labels,
                             chart_values=values)

    @app.route('/synergy/sync/<int:peer_id>/<int:course_id>')
    @login_required
    def synergy_sync(peer_id, course_id):
        user_id = session['user_id']
        db = g.db
        
        # Check if match already exists
        existing = db.execute('''
            SELECT id FROM synergy_matches 
            WHERE course_id = ? AND 
            ((user_a_id = ? AND user_b_id = ?) OR (user_a_id = ? AND user_b_id = ?))
        ''', (course_id, user_id, peer_id, peer_id, user_id)).fetchone()

        if not existing:
            db.execute('''
                INSERT INTO synergy_matches (user_a_id, user_b_id, course_id, match_reason)
                VALUES (?, ?, ?, ?)
            ''', (user_id, peer_id, course_id, "Manual Peer Request"))
            db.commit()
            flash("🤝 Synergy request created! You can now collaborate.", "success")
        else:
            flash("You already have an active sync with this peer.", "info")
            
        return redirect(url_for('synergy_connect'))

    @app.route('/synergy/update-meeting', methods=['POST'])
    @login_required
    def synergy_update_meeting():
        from flask import request
        match_id = request.form.get('match_id')
        link = request.form.get('meeting_link')
        g.db.execute('UPDATE synergy_matches SET meeting_link = ? WHERE id = ?', (link, match_id))
        g.db.commit()
        flash("Meeting link updated!", "success")
        return redirect(url_for('synergy_connect'))

    @app.route('/synergy/update-notes', methods=['POST'])
    @login_required
    def synergy_update_notes():
        from flask import request
        match_id = request.form.get('match_id')
        transcript = request.form.get('transcript', '')

        # Summarize using OpenAI
        summary = ""
        if transcript.strip():
            try:
                from openai import OpenAI
                client = OpenAI(api_key="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")
                
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "You are an AI assistant that summarizes meeting transcripts into concise bullet points focusing on learning objectives and action items."},
                        {"role": "user", "content": f"Please summarize this meeting transcript:\n\n{transcript}"}
                    ]
                )
                summary = response.choices[0].message.content
            except Exception as e:
                print("OpenAI Error:", e)
                summary = "Error generating summary: " + str(e)
        else:
            summary = "No transcript provided."

        g.db.execute('UPDATE synergy_matches SET sync_log = ? WHERE id = ?', (summary, match_id))
        g.db.commit()
        flash("AI Session notes summarized and updated!", "success")
        return redirect(url_for('synergy_connect'))
