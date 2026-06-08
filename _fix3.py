import re

with open('yue_ui.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the line with stage1_size Radio
for i, line in enumerate(lines):
    if 'stage1_size = gr.Radio(' in line:
        indent = '                    '
        # Get the closing line (Radio has 2 more lines normally)
        insert_lines = [
            indent + '# Use YuEGP checkbox - quantized model for longer songs on limited VRAM\n',
            indent + 'use_yuegp_cb = gr.Checkbox(\n',
            indent + '    label="Use YuEGP (quantized, for longer songs on 6GB+ VRAM)",\n',
            indent + '    value=True,\n',
            indent + ')\n',
        ]
        lines = lines[:i+5] + insert_lines + lines[i+5:]
        print('Added YuEGP checkbox at line', i)
        break

# Change seg_sl default from RTX profile to 2
for i, line in enumerate(lines):
    if 'seg_sl = gr.Slider' in line and 'value=RTX_3060_PROFILE' in line:
        lines[i] = line.replace('RTX_3060_PROFILE["run_n_segments"]', '2')
        print('Changed seg_sl default to 2')

# Change loop_cb default from False to True
for i, line in enumerate(lines):
    if 'loop_cb = gr.Checkbox' in line and 'value=False' in line:
        lines[i] = line.replace('value=False', 'value=True')
        print('Changed loop_cb to True')

with open('yue_ui.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
print('Done')
