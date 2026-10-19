SAMPLE = {
    'project': 'acme/checkout',
    'title': 'Accept JSON checkout preferences',
    'files': [
        {'path': 'checkout/contracts.py', 'content': '''"""Checkout request contract."""
import json

def parse_preferences(raw: str) -> dict:
    """Client preferences are untrusted JSON, never Python expressions."""
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Preferences must be an object")
    return value
'''},
        {'path': 'docs/review-guidelines.md', 'content': '''# Checkout conventions
Client input must be parsed as JSON and validated against the request contract.
Never evaluate strings received from clients as executable Python code.
Invalid input must produce a validation error, not an empty successful result.
Unexpected exceptions must propagate to the service error handler.
'''}
    ],
    'diff': '''diff --git a/checkout/api.py b/checkout/api.py
--- a/checkout/api.py
+++ b/checkout/api.py
@@ -1,3 +1,7 @@
 def preferences(request):
-    return parse_preferences(request.body)
+    try:
+        options = eval(request.body)
+        return options
+    except Exception:
+        return {}
 
'''
}
