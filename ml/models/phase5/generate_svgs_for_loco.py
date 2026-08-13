"""Generate SVG lifecycle plots for a given loco using plot_lifecycle_step.plot_wheelset."""
from pathlib import Path
import sys
from models.phase5 import plot_lifecycle_step

if len(sys.argv) < 2:
    print('usage: python generate_svgs_for_loco.py <loco_number>')
    sys.exit(2)

loco = sys.argv[1]
turns, wes = plot_lifecycle_step.load_data()
w = wes[wes['LomNumber'].astype(str) == str(loco)]
if w.empty:
    print('no wheelsets for loco', loco)
    sys.exit(1)

wheelsets = sorted(w['wheelset_equipment_id'].unique())
print('wheelsets:', wheelsets)
for ws in wheelsets:
    measurements = wes[wes['wheelset_equipment_id'] == ws].copy()
    events = turns[turns['wheelset_equipment_id'] == ws].copy()
    p = plot_lifecycle_step.plot_wheelset(int(ws), str(loco), measurements, events, plot_lifecycle_step.OUTPUT_DIR)
    svg_p = Path(p).with_suffix('.svg')
    if svg_p.exists():
        print('wrote', svg_p)
    else:
        print('failed to write svg for', ws)
print('done')
