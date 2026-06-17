from flask import render_template

def register_pages(app):


    @app.route('/help')
    def help_page():
        return render_template('pages/help.html')

    @app.route('/about')
    def about():
        return render_template('pages/about.html')

    @app.route('/terms')
    def terms():
        return render_template('pages/terms.html')

    @app.route('/privacy')
    def privacy():
        return render_template('pages/privacy.html')

    @app.route('/how-it-works')
    def how_it_works():
        return render_template('pages/how_it_works.html')





