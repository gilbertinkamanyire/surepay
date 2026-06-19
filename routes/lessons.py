import os
import json
from datetime import datetime
from flask import render_template, request, redirect, url_for, session, flash, g, abort, send_from_directory, current_app
from helpers import login_required, role_required, send_notification_email, log_attendance

def register_lessons(app):


    @app.route('/categories/<int:category_id>/lessons/<int:lesson_id>')
    @login_required
    def view_lesson(category_id, lesson_id):
        lesson = g.db.execute(
            'SELECT * FROM lessons WHERE id = ? AND category_id = ?',
            (lesson_id, category_id)
        ).fetchone()

        if not lesson:
            abort(404)

        # Log attendance for employees
        if session.get('role') == 'employee':
            log_attendance(session['user_id'], category_id, lesson_id, 'view')

        category = g.db.execute('SELECT * FROM categories WHERE id = ?', (category_id,)).fetchone()

        # Get all lessons for navigation
        all_lessons = g.db.execute(
            'SELECT id, title, order_num FROM lessons WHERE category_id = ? ORDER BY order_num',
            (category_id,)
        ).fetchall()

        # Find prev/next
        current_idx = None
        for i, l in enumerate(all_lessons):
            if l['id'] == lesson_id:
                current_idx = i
                break

        prev_lesson = all_lessons[current_idx - 1] if current_idx and current_idx > 0 else None
        next_lesson = all_lessons[current_idx + 1] if current_idx is not None and current_idx < len(all_lessons) - 1 else None

        # Check completion status
        progress = g.db.execute(
            'SELECT * FROM lesson_progress WHERE employee_id = ? AND lesson_id = ?',
            (session['user_id'], lesson_id)
        ).fetchone()

        # Find linked assessment (questionnaire) for this lesson, if any
        lesson_assessment = g.db.execute(
            'SELECT * FROM assessments WHERE category_id = ? AND lesson_id = ?',
            (category_id, lesson_id)
        ).fetchone()

        assessment_submitted = False
        if lesson_assessment and session.get('role') == 'employee':
            sub = g.db.execute(
                'SELECT * FROM submissions WHERE assessment_id = ? AND employee_id = ?',
                (lesson_assessment['id'], session['user_id'])
            ).fetchone()
            assessment_submitted = bool(sub)

        # Load bookmark and personal note for the current user (if any)
        bookmarked = False
        note_content = ''
        if session.get('user_id'):
            try:
                bm = g.db.execute('SELECT id FROM bookmarks WHERE user_id = ? AND lesson_id = ?', (session['user_id'], lesson_id)).fetchone()
                bookmarked = bool(bm)
            except Exception:
                bookmarked = False

            try:
                note_row = g.db.execute('SELECT content FROM personal_notes WHERE user_id = ? AND lesson_id = ?', (session['user_id'], lesson_id)).fetchone()
                note_content = note_row['content'] if note_row else ''
            except Exception:
                note_content = ''

        # Load Q&A for this lesson
        qa_items = g.db.execute('''
            SELECT qa.*, u.full_name as author_name, u.role as author_role
            FROM lesson_qa qa
            JOIN users u ON qa.user_id = u.id
            WHERE qa.lesson_id = ?
            ORDER BY qa.created_at DESC
        ''', (lesson_id,)).fetchall()

        return render_template('categories/lesson.html',
                             lesson=lesson,
                             category=category,
                             all_lessons=all_lessons,
                             prev_lesson=prev_lesson,
                             next_lesson=next_lesson,
                             is_completed=progress and progress['completed'],
                             lesson_assessment=lesson_assessment,
                             assessment_submitted=assessment_submitted,
                             bookmarked=bookmarked,
                             note_content=note_content,
                             qa_items=qa_items)


    @app.route('/categories/<int:category_id>/lessons/<int:lesson_id>/complete', methods=['POST'])
    @login_required
    def complete_lesson(category_id, lesson_id):
        # Mark lesson complete
        existing = g.db.execute(
            'SELECT * FROM lesson_progress WHERE employee_id = ? AND lesson_id = ?',
            (session['user_id'], lesson_id)
        ).fetchone()

        if existing:
            g.db.execute(
                'UPDATE lesson_progress SET completed = 1, completed_at = CURRENT_TIMESTAMP WHERE employee_id = ? AND lesson_id = ?',
                (session['user_id'], lesson_id)
            )
        else:
            g.db.execute(
                'INSERT INTO lesson_progress (employee_id, lesson_id, completed, completed_at) VALUES (?, ?, 1, CURRENT_TIMESTAMP)',
                (session['user_id'], lesson_id)
            )

        # Update category progress
        total_lessons = g.db.execute(
            'SELECT COUNT(*) FROM lessons WHERE category_id = ?', (category_id,)
        ).fetchone()[0]

        completed_lessons = g.db.execute('''
            SELECT COUNT(*) FROM lesson_progress lp
            JOIN lessons l ON lp.lesson_id = l.id
            WHERE lp.employee_id = ? AND l.category_id = ? AND lp.completed = 1
        ''', (session['user_id'], category_id)).fetchone()[0]

        progress = (completed_lessons / total_lessons * 100) if total_lessons > 0 else 0

        g.db.execute(
            'UPDATE enrollments SET progress = ?, last_lesson_id = ? WHERE employee_id = ? AND category_id = ?',
            (round(progress, 1), lesson_id, session['user_id'], category_id)
        )

        g.db.commit()
        flash('Lesson marked as complete!', 'success')
        return redirect(url_for('view_lesson', category_id=category_id, lesson_id=lesson_id))


    @app.route('/categories/<int:category_id>/lessons/<int:lesson_id>/bookmark', methods=['POST'])
    @login_required
    def toggle_bookmark(category_id, lesson_id):
        user_id = session.get('user_id')
        if not user_id:
            flash('Please log in to bookmark lessons.', 'info')
            return redirect(request.referrer or url_for('view_lesson', category_id=category_id, lesson_id=lesson_id))

        existing = g.db.execute('SELECT id FROM bookmarks WHERE user_id = ? AND lesson_id = ?', (user_id, lesson_id)).fetchone()
        try:
            if existing:
                g.db.execute('DELETE FROM bookmarks WHERE id = ?', (existing['id'],))
                g.db.commit()
                flash('Bookmark removed.', 'info')
            else:
                g.db.execute('INSERT INTO bookmarks (user_id, category_id, lesson_id) VALUES (?, ?, ?)', (user_id, category_id, lesson_id))
                g.db.commit()
                flash('Bookmarked lesson.', 'success')
        except Exception:
            flash('Could not update bookmark at this time.', 'danger')

        return redirect(request.referrer or url_for('view_lesson', category_id=category_id, lesson_id=lesson_id))


    @app.route('/categories/<int:category_id>/lessons/<int:lesson_id>/notes', methods=['POST'])
    @login_required
    def save_lesson_note(category_id, lesson_id):
        user_id = session.get('user_id')
        if not user_id:
            flash('Please log in to save notes.', 'info')
            return redirect(request.referrer or url_for('view_lesson', category_id=category_id, lesson_id=lesson_id))

        delete_flag = request.form.get('delete_note')
        content = request.form.get('note', '').strip()
        existing = g.db.execute('SELECT id FROM personal_notes WHERE user_id = ? AND lesson_id = ?', (user_id, lesson_id)).fetchone()
        try:
            if delete_flag:
                if existing:
                    g.db.execute('DELETE FROM personal_notes WHERE id = ?', (existing['id'],))
                    g.db.commit()
                    flash('Note deleted.', 'info')
            else:
                if content:
                    if existing:
                        g.db.execute('UPDATE personal_notes SET content = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?', (content, existing['id']))
                    else:
                        g.db.execute('INSERT INTO personal_notes (user_id, lesson_id, content) VALUES (?, ?, ?)', (user_id, lesson_id, content))
                    g.db.commit()
                    flash('Note saved.', 'success')
                else:
                    # empty content -> delete existing
                    if existing:
                        g.db.execute('DELETE FROM personal_notes WHERE id = ?', (existing['id'],))
                        g.db.commit()
                        flash('Note deleted.', 'info')
        except Exception:
            flash('Could not save note at this time.', 'danger')

        return redirect(request.referrer or url_for('view_lesson', category_id=category_id, lesson_id=lesson_id))


    @app.route('/categories/<int:category_id>/lessons/add', methods=['GET', 'POST'])
    @role_required('admin')
    def add_lesson(category_id):
        category = g.db.execute('SELECT * FROM categories WHERE id = ?', (category_id,)).fetchone()
        if not category:
            abort(404)

        if session['role'] != 'admin' and category['admin_id'] != session['user_id']:
            abort(403)

        if request.method == 'POST':
            title = request.form.get('title', '').strip()
            content = request.form.get('content', '').strip()
            order_num = request.form.get('order_num', 0, type=int)

            attachment = request.files.get('attachment')
            attachment_url = ''
            attachment_type = ''

            if attachment and attachment.filename:
                from werkzeug.utils import secure_filename
                filename = secure_filename(attachment.filename)
                ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
                unique_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                upload_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                attachment.save(upload_path)
                attachment_url = f"/uploads/{unique_filename}"
                attachment_type = ext

            is_hidden = 1 if request.form.get('is_hidden') else 0

            # Assessment Data
            assessment_title = request.form.get('assessment_title', '').strip()
            
            # Parse questions from form
            questions = []
            for q_index in range(10): # Limit to 10 in lesson add for simplicity, or more if needed
                q_text = request.form.get(f'question_{q_index}', '').strip()
                if not q_text:
                    continue

                options = []
                for o in range(4):
                    opt = request.form.get(f'option_{q_index}_{o}', '').strip()
                    options.append(opt)

                correct = request.form.get(f'correct_{q_index}', 0, type=int)

                questions.append({
                    'question': q_text,
                    'options': options,
                    'correct': correct
                })

            if not assessment_title or not questions:
                flash('An assessment title and at least one question are required.', 'danger')
            elif title and content:
                # Insert Lesson
                cursor = g.db.execute(
                    'INSERT INTO lessons (category_id, title, content, attachment_url, attachment_type, order_num, is_hidden) VALUES (?, ?, ?, ?, ?, ?, ?)',
                    (category_id, title, content, attachment_url, attachment_type, order_num, is_hidden)
                )
                lesson_id = cursor.lastrowid

                # Insert Assessment
                g.db.execute(
                    'INSERT INTO assessments (category_id, lesson_id, title, questions_json) VALUES (?, ?, ?, ?)',
                    (category_id, lesson_id, assessment_title, json.dumps(questions))
                )

                g.db.commit()
                send_notification_email(
                    subject=f"New Lesson Added in {category['title']}",
                    text_part=f"A new lesson '{title}' has been added to {category['title']}.",
                    html_part=f"<h3>New Lesson Added</h3><p>A new lesson <b>{title}</b> has been added to <b>{category['title']}</b>.</p>",
                    notify_roles=['student']
                )
                flash('Lesson and required assessment added successfully!', 'success')
                return redirect(url_for('category_detail', category_id=category_id))
            else:
                flash('Lesson title and content are required.', 'danger')

        # Get max order for default
        max_order = g.db.execute(
            'SELECT COALESCE(MAX(order_num), 0) + 1 FROM lessons WHERE category_id = ?',
            (category_id,)
        ).fetchone()[0]

        return render_template('categories/add_lesson.html', category=category, max_order=max_order)


    @app.route('/categories/<int:category_id>/lessons/<int:lesson_id>/edit', methods=['GET', 'POST'])
    @role_required('admin')
    def edit_lesson(category_id, lesson_id):
        lesson = g.db.execute(
            'SELECT * FROM lessons WHERE id = ? AND category_id = ?',
            (lesson_id, category_id)
        ).fetchone()

        if not lesson:
            abort(404)

        category = g.db.execute('SELECT * FROM categories WHERE id = ?', (category_id,)).fetchone()

        if request.method == 'POST':
            title = request.form.get('title', '').strip()
            content = request.form.get('content', '').strip()
            order_num = request.form.get('order_num', 0, type=int)

            attachment = request.files.get('attachment')
            is_hidden = 1 if request.form.get('is_hidden') else 0
            
            if title and content:
                if attachment and attachment.filename:
                    from werkzeug.utils import secure_filename
                    filename = secure_filename(attachment.filename)
                    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
                    unique_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                    upload_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                    attachment.save(upload_path)
                    attachment_url = f"/uploads/{unique_filename}"
                    attachment_type = ext

                    g.db.execute(
                        'UPDATE lessons SET title=?, content=?, attachment_url=?, attachment_type=?, order_num=?, is_hidden=? WHERE id=?',
                        (title, content, attachment_url, attachment_type, order_num, is_hidden, lesson_id)
                    )
                else:
                    g.db.execute(
                        'UPDATE lessons SET title=?, content=?, order_num=?, is_hidden=? WHERE id=?',
                        (title, content, order_num, is_hidden, lesson_id)
                    )
                g.db.commit()
                flash('Lesson updated!', 'success')
                return redirect(url_for('view_lesson', category_id=category_id, lesson_id=lesson_id))

        return render_template('categories/edit_lesson.html', lesson=lesson, category=category)


    @app.route('/categories/<int:category_id>/lessons/<int:lesson_id>/delete', methods=['POST'])
    @role_required('admin')
    def delete_lesson(category_id, lesson_id):
        g.db.execute('DELETE FROM lessons WHERE id = ? AND category_id = ?', (lesson_id, category_id))
        g.db.commit()
        flash('Lesson deleted.', 'info')
        return redirect(url_for('category_detail', category_id=category_id))


    @app.route('/categories/<int:category_id>/lessons/<int:lesson_id>/download')
    @login_required
    def download_resource(category_id, lesson_id):
        lesson = g.db.execute(
            'SELECT attachment_url FROM lessons WHERE id = ? AND category_id = ?',
            (lesson_id, category_id)
        ).fetchone()

        if not lesson or not lesson['attachment_url']:
            flash('Resource not found.', 'danger')
            return redirect(url_for('view_lesson', category_id=category_id, lesson_id=lesson_id))

        # Log attendance
        if session.get('role') == 'student':
            log_attendance(session['user_id'], category_id, lesson_id, 'download')

        filename = lesson['attachment_url'].split('/')[-1]
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

    @app.route('/categories/<int:category_id>/lessons/<int:lesson_id>/qa/ask', methods=['POST'])
    @login_required
    def ask_lesson_question(category_id, lesson_id):
        question_text = request.form.get('question', '').strip()
        if not question_text:
            flash('Please enter a question.', 'danger')
        else:
            g.db.execute(
                'INSERT INTO lesson_qa (lesson_id, user_id, question) VALUES (?, ?, ?)',
                (lesson_id, session['user_id'], question_text)
            )
            g.db.commit()
            flash('Your question has been posted!', 'success')
        return redirect(url_for('view_lesson', category_id=category_id, lesson_id=lesson_id) + '#qa-section')

    @app.route('/categories/<int:category_id>/lessons/<int:lesson_id>/qa/<int:qa_id>/answer', methods=['POST'])
    @login_required
    def answer_lesson_question(category_id, lesson_id, qa_id):
        answer_text = request.form.get('answer', '').strip()
        if not answer_text:
            flash('Please enter an answer.', 'danger')
        else:
            g.db.execute('UPDATE lesson_qa SET answer = ? WHERE id = ?', (answer_text, qa_id))
            g.db.commit()
            flash('Answer posted!', 'success')
        return redirect(url_for('view_lesson', category_id=category_id, lesson_id=lesson_id) + '#qa-section')

    @app.route('/api/generate_lesson_from_pdf', methods=['POST'])
    @login_required
    def generate_lesson_from_pdf():
        if session.get('role') not in ('admin', 'lecturer'):
            return {"error": "Unauthorized"}, 403
            
        pdf_file = request.files.get('pdf_file')
        if not pdf_file:
            return {"error": "No PDF file provided"}, 400
            
        try:
            import PyPDF2
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
                
            text = text[:15000] # Limit to avoid token limit
            
            from openai import OpenAI
            client = OpenAI(api_key=current_app.config['OPENAI_API_KEY'])
            
            prompt = f"""
You are an expert curriculum designer. Extract the key learning objectives from the following text and generate a structured lesson and a 5-question multiple choice quiz.
Return ONLY a valid JSON object with the following structure:
{{
  "title": "A catchy title for the lesson",
  "content": "<p>HTML formatted lesson content</p>",
  "assessment_title": "Quiz Title",
  "questions": [
    {{
      "question": "The question text",
      "options": ["A", "B", "C", "D"],
      "correct": 0
    }}
  ]
}}

Source Text:
{text}
"""
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                response_format={ "type": "json_object" }
            )
            
            result = response.choices[0].message.content
            return result, 200, {'Content-Type': 'application/json'}
            
        except Exception as e:
            print("Error generating lesson:", e)
            return {"error": str(e)}, 500


