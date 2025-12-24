# music-gradebook (demo)

Minimal Django gradebook demo for a musical school (RU interface).

## Features (demo)
- Auth (Django username/password)
- Roles via Profile: ADMIN / TEACHER / STUDENT / PARENT
- Courses: instrument / ensemble / theory
- Enrollments, teacher assignment
- Assessments + Grades (score + optional comment)
- Student/Parent view: assessments + grades + computed average
- Teacher view: grade-entry table (students x assessments)
- Admin: link to Django admin
- Demo seed command: idempotent

## Setup (local)

```bash
cd music-gradebook

python -m venv .venv
# Windows:
# .venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

pip install -r requirements.txt

python manage.py migrate
python manage.py seed_demo
python manage.py runserver
