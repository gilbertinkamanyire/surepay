from flask import render_template, request, redirect, url_for, flash, g, abort
from helpers import role_required

def register_departments(app):

    @app.route('/admin/departments', methods=['GET', 'POST'])
    @role_required('admin')
    def manage_departments():
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            
            if name:
                try:
                    g.db.execute(
                        'INSERT INTO departments (name, description) VALUES (?, ?)',
                        (name, description)
                    )
                    g.db.commit()
                    flash(f'Department "{name}" created successfully!', 'success')
                except Exception as e:
                    flash(f'Error creating department: {e}', 'danger')
            else:
                flash('Department name is required.', 'danger')
        
        departments = g.db.execute('SELECT * FROM departments ORDER BY name').fetchall()
        return render_template('admin/departments.html', departments=departments)

    @app.route('/admin/departments/<int:dept_id>/edit', methods=['GET', 'POST'])
    @role_required('admin')
    def edit_department(dept_id):
        dept = g.db.execute('SELECT * FROM departments WHERE id = ?', (dept_id,)).fetchone()
        if not dept:
            abort(404)
            
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            
            if name:
                g.db.execute(
                    'UPDATE departments SET name = ?, description = ? WHERE id = ?',
                    (name, description, dept_id)
                )
                g.db.commit()
                flash('Department updated successfully!', 'success')
                return redirect(url_for('manage_departments'))
        
        return render_template('admin/edit_department.html', dept=dept)

    @app.route('/admin/departments/<int:dept_id>/delete', methods=['POST'])
    @role_required('admin')
    def delete_department(dept_id):
        # Check if any courses are linked
        has_courses = g.db.execute('SELECT id FROM courses WHERE department_id = ?', (dept_id,)).fetchone()
        if has_courses:
            flash('Cannot delete department because it has linked course units.', 'danger')
        else:
            g.db.execute('DELETE FROM departments WHERE id = ?', (dept_id,))
            g.db.commit()
            flash('Department deleted.', 'success')
        return redirect(url_for('manage_departments'))
