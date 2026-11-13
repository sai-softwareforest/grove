# The log format tally reads

Common log format with one extra field at the end, the response time in
seconds:

    203.0.113.9 - - [10/Oct/2026:13:55:36 +0000] "GET /search?q=a HTTP/1.1" 200 2326 0.012

`ParseLine` finds the first "[" and the quotes. An IPv6 address written
in brackets therefore breaks it. The combined format (with referrer and
user agent) is not read either.
