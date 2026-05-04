import os
import re

def fix_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    pattern = r'(templates\.TemplateResponse\(\s*)(["\'][^"\']+["\'])(\s*,\s*)({|context=)'
    
    def replacer(match):
        prefix = match.group(1)
        name_str = match.group(2)
        comma = match.group(3)
        context_start = match.group(4)
        return f'{prefix}request=request, name={name_str}, context={context_start}'

    new_content = re.sub(pattern, replacer, content)
    
    if new_content != content:
        with open(filepath, 'w') as f:
            f.write(new_content)
        print(f"Fixed {filepath}")

for root, _, files in os.walk('app'):
    for file in files:
        if file.endswith('.py'):
            fix_file(os.path.join(root, file))
