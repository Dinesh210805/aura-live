;;import re, sys

with open(r'd:\PROJECTS\Aura_agent - Phase 2\logs\command_log_20260225_213534_491127.html', encoding='utf-8') as f:
    content = f.read()

clean = re.sub(r'<[^>]+>', '', content)
for ent, rep in [('&quot;','"'),('&amp;','&'),('&#x2705;','OK'),('&#x25B6;','>'),('&#x26A1;','!'),('&#x1F4CB;','[PLAN]'),('&#x1F916;','[BOT]'),('&#x1F441;','[VLM]'),('&#x2714;','[done]')]:
    clean = clean.replace(ent, rep)

patterns = [
    'GESTURE #', 'SUBGOAL_START', 'SUBGOAL_COMPLETE', 'PLAN_CREATED',
    'VLM #', 'LLM #', 'COMMAND', 'press_enter', 'method.*keyevent',
    'keyevent', 'skipped.*WebView', 'action key', 'task_comp',
    'screen_changed', 'verification_reason', 'Target match', 'TAPPED',
    'action_type', 'description', 'method.*key', 'kv-row', 'kv-val'
]

hits = []
for line in clean.split('\n'):
    t = line.strip()
    if not t:
        continue
    for p in patterns:
        if re.search(p, t, re.I):
            hits.append(t[:250])
            break

for h in hits[:150]:
    print(h)
import sys; sys.stdout.flush()
