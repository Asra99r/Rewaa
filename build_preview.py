from pathlib import Path
import shutil
p=Path(__file__).parent
out=p/'dist';out.mkdir(exist_ok=True)
shutil.copytree(p/'static',out/'static',dirs_exist_ok=True)
h=(p/'static/index.html').read_text().replace('<script src="/static/app.js">','<script src="/static/preview-adapter.js"></script>\n  <script src="/static/app.js">')
(out/'index.html').write_text(h)
