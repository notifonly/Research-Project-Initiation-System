import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
html = (ROOT / "index_standalone.html").read_text(encoding="utf-8")
print(f"Read HTML: {len(html)} chars")

# Encode as base64 for safe transfer
import base64
b64 = base64.b64encode(html.encode("utf-8")).decode("ascii")

# Create JS that decodes and writes
js = f"""
(function() {{
  var html = atob("{b64}");
  var decoder = new TextDecoder('utf-8');
  var decoded = new TextDecoder('utf-8').decode(Uint8Array.from(atob("{b64}"), c => c.charCodeAt(0)));
  document.open();
  document.write(decoded);
  document.close();
}})();
"""

(ROOT / "load_dash.js").write_text(js, encoding="utf-8")
print(f"Wrote load_dash.js: {len(js)} chars")
