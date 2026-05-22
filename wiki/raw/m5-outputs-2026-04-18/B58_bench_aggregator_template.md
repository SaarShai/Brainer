---
type: raw
source: deepseek-r1:32b
date: 2026-04-19
tags: [m5-generated, round10]
---

```python
"""
Jinja2 Template for REPORT.md
"""

# Report Header
# =============
# Overview of test results, environment, and key metrics

# Headline Numbers Section
# ------------------------
# Key summary metrics in table format
## Headline Metrics
| Metric | Value | Status |
|--------|-------|--------|
{% for metric in headline_metrics %}
| {{metric.name}} | {{metric.value}} | {% if metric.status == 'pass' %}✅{% else %}❌{% endif %} |
{% endfor %}

# Per-Category Results Section
# ----------------------------
## Test Results by Category
{% for category in categories %}
### {{category.name}}
{% if category.tests %}
| Test Case | Status | Duration (s) |
|-----------|--------|--------------|
{% for test in category.tests %}
| {{test.name}} | {% if test.status == 'pass' %}✅{% else %}❌{% endif %} | {{test.duration:.2f}} |
{% endfor %}
{% else %}
No tests found in this category.
{% endif %}

# Regression Alerts Section
# -------------------------
## Regression Alerts
{% if regression_alerts %}
{% for alert in regression_alerts %}
⚠️ **{{alert.component}}**: {{alert.description}}  
Severity: **{{alert.severity}}**  
{% endfor %}
{% else %}
No regression alerts detected.
{% endif %}

# Trend vs Last Run Section
# -------------------------
## Trends Compared to Previous Run
| Metric | Current Value | Previous Value | Change |
|--------|---------------|----------------|--------|
{% for trend in trends %}
| {{trend.metric}} | {{trend.current}} | {{trend.previous}} | {% if trend.change >= 0 %}+{{trend.change:.2f}}% (↑){% else %}{{trend.change:.2f}}% (↓){% endif %} |
{% endfor %}
```

This template provides:
1. A clear, markdown-formatted report structure
2. Headline metrics table for quick overview
3. Detailed per-category test results
4. Highlighted regression alerts with severity
5. Trend analysis with visual indicators

The template uses Jinja2 features like loops and conditionals to handle dynamic data. Statuses are shown with emoji (✅/❌), and trends use color-coded arrows (+/-) for quick comprehension.

To use this template:
1. Pass test_results, regression_alerts, and trends as context variables
2. Ensure consistent data structures in your Python code
3. Customize styling or formatting as needed

The report is designed to be easily readable in markdown format while maintaining technical precision and visual clarity.
