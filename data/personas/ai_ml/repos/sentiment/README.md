---
id: "rd-ai_ml-sentiment"
type: "readme"
persona: "ai_ml"
project: "sentiment"
skills: ["NLP", "Hugging Face", "transformers", "PyTorch"]
date: "2023-10-01"
client_industry: "ecommerce"
synthetic: true
---
# sentiment

Review sentiment classifier - technical notes.

Stack: NLP, Hugging Face, transformers, PyTorch.

## Setup
```
make install && make run
```

## Notes
Result in production: fine-tuned a DistilBERT model to 0.91 F1 on 50k product reviews.

