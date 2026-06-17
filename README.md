# SurePay Learn &mdash; E-Learning Platform

SurePay Learn is a lightweight, highly-efficient learning management system designed specifically for the African context, prioritizing low-bandwidth environments, mobile accessibility, and peer-to-peer collaboration.

## 🌟 Unique AI-Powered Features

### 🧠 Cognitive Mirror
*The Cognitive Mirror* acts as an intelligent reflection of a student's unique learning journey, analyzing their behavior to provide actionable insights.
- **Peak Focus Window:** By tracking attendance timestamps and lesson views, the system calculates the time of day a student is most active and focused (e.g., "Early Bird 🌅", "Night Owl 🦉").
- **Knowledge Strongholds:** Identifies topics the student has mastered quickly based on direct quiz completions and swift lesson progression.
- **Critical Reflection Points:** Detects areas where a student is struggling by tracking repeated lesson views (e.g., viewing a lesson 3+ times without passing the assessment). The system then suggests seeking help on these specific topics.
- **AI Learning Insights:** A continuous feed of personalized learning recommendations generated based on the student's unique interaction data.

### 🤝 Synergy Connect
*Synergy Connect* is a peer-to-peer matching system designed to foster collaborative learning environments even when students are studying remotely.
- **Smart Matching:** The system compares the progress of all students enrolled in a particular course.
- **Mentors vs. Learners:** It identifies peers who are further ahead ("Potential Mentors") and peers who are slightly behind ("Potential Learners"). 
- **15-Minute Syncs:** Students can initiate rapid "Sync Requests" with their matched peers to engage in quick, 15-minute peer tutoring sessions to get unstuck on specific topics, fostering a community-driven safety net.

## 🚀 Core Platform Innovations

### 1. Zero-JavaScript / Low-Bandwidth Architecture
SurePay Learn is built to function flawlessly even on 2G networks. 
- **Pure CSS UI:** Complex UI components (like Tabs, Modals, and Accordions) are built entirely with HTML checkboxes/radio buttons and CSS, requiring absolutely no heavy JavaScript libraries to run.
- **Bandwidth Modes:** Users can toggle between "Standard", "Low Data", and "Ultra-Low Data" modes. The UI dynamically adjusts by stripping out heavy styling, suppressing animations, and filtering images to grayscale to save on data transfer.

### 2. Comprehensive Role Management
- **Students:** Can enroll in courses, view lessons (which automatically tracks attendance points), take assessments, and view their Cognitive Mirror.
- **Lecturers:** Can create courses, manage hidden/visible states for individual lessons and assignments, and review detailed submissions.
- **Admins:** Have a powerful overarching dashboard with "Danger Zone" controls to wipe test data, manage all user roles, verify new lecturer accounts manually, and view system-wide analytics.

### 3. Integrated Assessment & Attendance Logging
- **Attendance as Engagement:** Attendance isn't just logging in; it's tracked through active participation. Downloading a resource file or viewing a specific lesson module instantly logs attendance and awards "Participation Points".
- **Transparent Progress:** Every course member can see a dedicated "Participants" tab showing exactly where everyone stands, gamifying progress and encouraging students to keep up with their peers.

## 🖥️ Running Locally

SurePay Learn runs on **Windows, macOS, and Linux**. Local development uses SQLite (no database server required). PostgreSQL/gunicorn are only used for Linux production deployments and are skipped automatically on Windows.

### Windows (one click)

Double-click **`run.bat`** in the project folder. It creates a virtual environment, installs dependencies, and starts the app at <http://127.0.0.1:5000>.

### Windows (manual)

```bat
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Then open <http://127.0.0.1:5000>. The SQLite database (`database.db`) is created automatically on first run.

> **Note:** Use a recent Python that has wheels available for your platform (Python 3.10–3.13 recommended). On the latest bleeding-edge releases some binary packages may not yet ship wheels.

## ☁️ Deploying to Render (persistent data)

A [`render.yaml`](render.yaml) Blueprint is included. It provisions a managed
**PostgreSQL** database and the web service, and wires `DATABASE_URL` plus a
generated `SECRET_KEY` automatically. With Postgres, **data persists across
deploys** (plain SQLite on Render's filesystem is wiped on every redeploy).

1. Push this repo to GitHub (already done).
2. Render Dashboard → **New + → Blueprint** → select this repo → **Apply**.
3. The app auto-detects `DATABASE_URL` and creates its schema on first boot
   (`db_compat.py` / `models.py`) — no manual DB setup needed.
4. Register your admin account once on the fresh database.

Already have a service? Just add the database's **Internal Database URL** as a
`DATABASE_URL` environment variable on the existing web service and redeploy.

> Uploaded files (logos, lesson attachments) still reset unless you also attach
> a persistent disk — see the commented `disk:` block in `render.yaml`.
