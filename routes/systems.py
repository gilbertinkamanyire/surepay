from flask import render_template, request, redirect, url_for, flash, g, abort
from helpers import role_required

def register_systems(app):

    @app.route('/admin/systems', methods=['GET', 'POST'])
    @role_required('admin')
    def manage_systems():
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            
            if name:
                try:
                    g.db.execute(
                        'INSERT INTO systems (name, description) VALUES (?, ?)',
                        (name, description)
                    )
                    g.db.commit()
                    flash(f'system "{name}" created successfully!', 'success')
                except Exception as e:
                    flash(f'Error creating system: {e}', 'danger')
            else:
                flash('system name is required.', 'danger')
        
        systems = g.db.execute('SELECT * FROM systems ORDER BY name').fetchall()
        return render_template('admin/systems.html', systems=systems)

    @app.route('/admin/systems/<int:cat_id>/edit', methods=['GET', 'POST'])
    @role_required('admin')
    def edit_system(cat_id):
        cat = g.db.execute('SELECT * FROM systems WHERE id = ?', (cat_id,)).fetchone()
        if not cat:
            abort(404)
            
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            
            if name:
                g.db.execute(
                    'UPDATE systems SET name = ?, description = ? WHERE id = ?',
                    (name, description, cat_id)
                )
                g.db.commit()
                flash('system updated successfully!', 'success')
                return redirect(url_for('manage_systems'))
        
        return render_template('admin/edit_system.html', cat=cat)

    @app.route('/admin/systems/<int:cat_id>/delete', methods=['POST'])
    @role_required('admin')
    def delete_system(cat_id):
        # Check if any categories are linked
        has_categories = g.db.execute('SELECT id FROM categories WHERE system_id = ?', (cat_id,)).fetchone()
        if has_categories:
            flash('Cannot delete system because it has linked category units.', 'danger')
        else:
            g.db.execute('DELETE FROM systems WHERE id = ?', (cat_id,))
            g.db.commit()
            flash('system deleted.', 'success')
        return redirect(url_for('manage_systems'))
