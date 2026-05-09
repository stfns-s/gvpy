{% W = 8 %}
{% for i in range(W): %}
wire [{{ W-1 }}:0] r{{ i }};
{% endfor %}
