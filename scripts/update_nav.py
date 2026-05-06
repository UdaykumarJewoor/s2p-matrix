import os
import glob
import re

NAV_ITEMS = [
    ('dashboard', 'index.html', 'fa-chart-pie', 'Dashboard'),
    ('vendors', 'pages/vendors.html', 'fa-building', 'Vendors'),
    ('ai_discovery', 'pages/ai_discovery.html', 'fa-robot', 'AI Discovery'),
    ('rfq', 'pages/rfq.html', 'fa-file-alt', 'RFQ'),
    ('quotations', 'pages/quotations.html', 'fa-balance-scale', 'Quotations'),
    ('negotiations', 'pages/negotiations.html', 'fa-handshake', 'Negotiations'),
    ('contracts', 'pages/contracts.html', 'fa-file-signature', 'Contracts'),
    ('po', 'pages/purchase_orders.html', 'fa-shopping-cart', 'Purchase Orders'),
    ('grn', 'pages/grn.html', 'fa-truck-loading', 'Goods Receipt'),
    ('invoices', 'pages/invoices.html', 'fa-file-invoice', 'Invoices'),
    ('payments', 'pages/payments.html', 'fa-money-bill-wave', 'Payments'),
    ('performance', 'pages/performance.html', 'fa-star', 'Performance'),
    ('checklists', 'pages/checklists.html', 'fa-tasks', 'Checklists'),
    ('audit', 'pages/audit.html', 'fa-history', 'Audit Trail'),
    ('workflow', 'pages/workflow.html', 'fa-project-diagram', 'Pipeline Runner'),
    ('sap_integration', 'pages/sap_integration.html', 'fa-plug', 'SAP Integration')
]

def generate_nav(is_in_pages, current_file_key):
    lines = ['<nav class="sidebar-nav">']
    for key, path, icon, label in NAV_ITEMS:
        # Resolve paths recursively correctly
        if is_in_pages:
            if path == 'index.html':
                href = '../index.html'
            else:
                href = path.replace('pages/', '')
        else:
            href = path

        active_cls = ' active' if key == current_file_key else ''
        lines.append(f'      <a href="{href}" class="nav-item{active_cls}" data-page="{key}">')
        lines.append(f'        <i class="fa {icon}"></i><span>{label}</span>')
        lines.append(f'      </a>')
    lines.append('    </nav>')
    return '\n'.join(lines)


html_files = glob.glob('frontend/**/*.html', recursive=True)
count = 0

for file_path in html_files:
    filename = os.path.basename(file_path)
    is_in_pages = 'pages' in os.path.dirname(file_path).replace('\\', '/')

    # Determine current page key
    current_key = None
    for k, p, i, l in NAV_ITEMS:
        if filename in p:
            current_key = k
            break
            
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Regex to replace the <nav class="sidebar-nav"> ... </nav> block
    new_nav = generate_nav(is_in_pages, current_key)
    
    # We use re.sub with DOTALL to replace the entire <nav class="sidebar-nav">...</nav> block
    new_content = re.sub(r'<nav class="sidebar-nav">.*?</nav>', new_nav, content, flags=re.DOTALL)
    
    if content != new_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f'Updated side-nav in {file_path}')
        count += 1
    else:
        print(f'No change needed or <nav> not found in {file_path}')

print(f'Done! Updated {count} files.')
