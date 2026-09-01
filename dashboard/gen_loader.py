import json
html = open("D:/program/AIscience/dashboard/index_standalone.html", "r", encoding="utf-8").read()
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

with open("D:/program/AIscience/dashboard/load_dash.js", "w", encoding="utf-8") as f:
    f.write(js)
print(f"Wrote load_dash.js: {len(js)} chars")
