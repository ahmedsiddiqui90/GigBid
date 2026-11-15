---
id: "rd-fullstack-marketplace"
type: "readme"
persona: "fullstack"
project: "marketplace"
skills: ["Django", "Celery", "Redis", "PostgreSQL"]
date: "2023-10-01"
client_industry: "ecommerce"
synthetic: true
---
# marketplace

Django services marketplace - technical notes.

Stack: Django, Celery, Redis, PostgreSQL.

## Setup
```
make install && make run
```

## Notes
Result in production: built background order processing handling 15k orders a day.

