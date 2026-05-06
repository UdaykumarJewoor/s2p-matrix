import os
import glob
import re

LOGO_BLOCK = """    <div class="sidebar-header">
      <div class="logo-icon"><i class="fa-solid fa-network-wired"></i></div>
      <div class="logo-text">
        <span class="logo-main">HG INFO TECH</span>
        <span class="logo-sub">S2P Workflow Automation</span>
      </div>
    </div>"""

html_files = glob.glob('frontend/**/*.html', recursive=True)
count = 0

# The regex matches <div class="sidebar-header"> up to its matching closing </div>
# We assume the closing </div> is the first one after the inner content.
# Since the inner content contains nested <div>s, a simple .*?</div> might stop too early if there's a nested </div>.
# Looking at the original:
# <div class="sidebar-header">
#   <div class="logo-icon"><i class="..."></i></div>
#   <div class="logo-text">
#     <span class="logo-main">...</span>
#     <span class="logo-sub">...</span>
#   </div>
# </div>
# In this specific case, we can match up to `<nav class="sidebar-nav">` or just build a robust regex because right after sidebar-header is usually a blank line then `<nav class="sidebar-nav">`.

for file_path in html_files:
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Regex: find <div class="sidebar-header">, then anything, up until \s*<nav class="sidebar-nav">
    # This precisely captures the whole header block without worrying about nested divs.
    pattern = r'(<div class="sidebar-header">.*?)(?=\n\s*<nav class="sidebar-nav">)'
    new_content = re.sub(pattern, LOGO_BLOCK, content, flags=re.DOTALL)
    
    if content != new_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f'Updated logo in {file_path}')
        count += 1
    else:
        print(f'No change needed or block not found in {file_path}')

print(f'Done! Updated {count} files.')
