from flask import g

def log_attendance(user_id, course_id, lesson_id, activity_type):
    """Log a student's activity and award participation points."""
    g.db.execute(
        'INSERT INTO attendance (user_id, course_id, lesson_id, activity_type) VALUES (?, ?, ?, ?)',
        (user_id, course_id, lesson_id, activity_type)
    )

    # Update participation points in enrollments (1 point per action)
    g.db.execute('''
        UPDATE enrollments 
        SET participation_points = participation_points + 1 
        WHERE employee_id = ? AND course_id = ?
    ''', (user_id, course_id))

    g.db.commit()
