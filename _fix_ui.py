#!/usr/bin/env python
"""Fix yue_ui.py defaults:
1. Add use_yuegp checkbox after stage1_size Radio
2. Change seg_sl default from 1 to 2
3. Change loop_cb default from False to True
4. Add use_yuegp param to run_generation_stream
5. Add use_yuegp to gen_btn.click inputs
"""

import re

with open('yue_ui.py', 'r', encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')
new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    new_lines.append(line)
    
    # 1. Add use_yuegp checkbox after stage1_size Radio (after line 714)
    if 'stage1_size = gr.Radio(' in line:
        # Add the YuEGP checkbox after the Radio closes
        # Need to find where the Radio ends
        j = i + 1
        while j < len(lines) and ')' not in lines[j]:
            j += 1
        # Now at closing line, add checkbox after it
        indent = '                    '
        new_lines.append(indent + '# Use YuEGP checkbox - quantized model for longer songs on limited VRAM')
        new_lines.append(indent + 'use_yuegp_cb = gr.Checkbox(')
        new_lines.append(indent + '    label="Use YuEGP (quantized, for longer songs on 6GB+ VRAM)",')
        new_lines.append(indent + '    value=True,')
        new_lines.append(indent + ')')
        i = j
        
    # 2. Change seg_sl default from profile to 2
    if 'seg_sl = gr.Slider' in line and 'value=RTX_3060_PROFILE' in line:
        new_lines[-1] = line.replace('RTX_3060_PROFILE["run_n_segments"]', '2')
        
    # 3. Change loop_cb default from False to True
    if 'loop_cb = gr.Checkbox' in line and 'value=False' in line:
        new_lines[-1] = line.replace('value=False', 'value=True')
        
    # 4. Add use_yuegp param to run_generation_stream after loop_bars_in
    if 'loop_bars_in,' in line and '# post-processing' in lines[i+1]:
        new_lines.append('    # YuEGP option')
        new_lines.append('    use_yuegp,')
        
    # 5. Add use_yuegp to gen_btn.click inputs (before stem_cb)
    if 'loop_cb, loop_bars_in,' in line:
        new_lines.append(line)
        new_lines.append('                use_yuegp_cb,')
        i += 1
        
    i += 1

# Write back
with open('yue_ui.py', 'w', encoding='utf-8') as f:
    f.write('\n'.join(new_lines))

print('yue_ui.py defaults fixed successfully')
