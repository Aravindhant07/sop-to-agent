# Discovery report: {{ spec.name }}

Generated {{ generated }} from {{ spec.documents | join(", ") }}.

**{{ spec.rules | length }} rules extracted** · **{{ issues | length }} issues** ({{ counts.get("high", 0) }} high, {{ counts.get("medium", 0) }} medium, {{ counts.get("low", 0) }} low) · **{{ tests | length }} tests** ({{ open_tests }} depend on open issues)

## Questions for the customer

{% for i in issues %}
### {{ i.id }} · {{ i.severity | upper }} · {{ i.kind.replace("_", " ") }}

**{{ i.title }}**

{{ i.question }}

{% for sid in i.sentence_ids %}
{% if sid in sentences %}
> {{ sentences[sid].text }} *({{ sentences[sid].section or sentences[sid].doc }}, {{ sid }})*
{% endif %}
{% endfor %}
{% if i.examples %}
Example input: `{{ i.examples[0] }}`
{% endif %}
{% if i.detail %}
<sub>{{ i.detail }}</sub>
{% endif %}

{% endfor %}
## Extracted rules (in order)

| # | Rule | Outcome | Source |
|---|---|---|---|
{% for r in spec.rules %}
| {{ r.id }} | {{ r.condition | describe }}{% if r.priority != "normal" %} *({{ r.priority }})*{% endif %} | {{ r.outcome }} | {{ r.citation.quote if r.citation else "" }} |
{% endfor %}
{% if rejected %}

## Sentences that could not be turned into rules

{% for x in rejected %}
- {{ x.text }}: *{{ x.reason }}*
{% endfor %}
{% endif %}
