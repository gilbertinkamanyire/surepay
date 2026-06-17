import os
import glob

def fix_ids(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    content = content.replace("lecturer_id", "admin_id")
    content = content.replace("student_id", "employee_id")

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

for filepath in glob.glob('routes/*.py'):
    fix_ids(filepath)
    
print("Replaced ids in routes")
