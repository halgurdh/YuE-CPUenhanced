with open('yue_ui.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'label="Use YuEGP' in line and 'value=' not in line:
        lines[i] = line.replace('value=False,', 'value=True,\n')
    if 'run_n_segments"], step=1' in line:
        lines[i] = line.replace('value=RTX_3060_PROFILE["run_n_segments"],', 'value=2,')
    if 'label="Enable Loop Mode"' in line and 'value=False' in line:
        lines[i] = line.replace('value=False', 'value=True')

with open('yue_ui.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
print('Fixed')
