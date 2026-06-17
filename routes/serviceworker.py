from flask import jsonify, send_from_directory

def register_serviceworker(app):


    @app.route('/manifest.json')
    def manifest():
        return jsonify({
            "name": "SurePay - Online Learning",
            "short_name": "SurePay",
            "description": "Lightweight learning platform for Uganda",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#fffaf5",
            "theme_color": "#f97316",
            "icons": []
        })

    @app.route('/sw.js')
    def sw():
        return send_from_directory('static', 'sw.js')


