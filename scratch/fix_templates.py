import os
import glob

def fix_template(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    content = content.replace("Lecturer", "Trainer") # Display name
    content = content.replace("lecturer", "admin") # Variables / IDs
    content = content.replace("Student", "Employee")
    content = content.replace("student", "employee")
    
    # Capitalize replacements for UI
    content = content.replace("Trainer_id", "admin_id") # Fix case issue caused by Lecturer -> Trainer
    content = content.replace("Employee_id", "employee_id") 

    # Clean up any bad replacements
    content = content.replace("employee.html", "student.html") # Leave template filenames for now or I'll have to rename files

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

for root, _, files in os.walk('templates'):
    for file in files:
        if file.endswith('.html'):
            fix_template(os.path.join(root, file))
            
print("Replaced strings in templates")
