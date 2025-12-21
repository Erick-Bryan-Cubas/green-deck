import json
from prompts import SUPERMEMO_RULES, BASIC_CARDS_PROMPT

training_examples = [
    {
        "text": "Machine learning is a subset of artificial intelligence that enables systems to learn and improve from experience without being explicitly programmed.",
        "output": json.dumps([
            {"front": "What is machine learning?", "back": "A subset of AI that enables systems to learn from experience without explicit programming.", "deck": "CS/AI"},
            {"front": "What is the primary focus of machine learning?", "back": "Developing algorithms that access data and learn autonomously.", "deck": "CS/AI"}
        ])
    },
    {
        "text": "The Dead Sea is a salt lake located on the border between Israel and Jordan. Its shoreline is the lowest point on Earth's surface, averaging 396 m below sea level.",
        "output": json.dumps([
            {"front": "Where is the Dead Sea located?", "back": "On the border between Israel and Jordan.", "deck": "Geography"},
            {"front": "What is the lowest point on Earth's surface?", "back": "The Dead Sea shoreline.", "deck": "Geography"},
            {"front": "What is the average level of the Dead Sea?", "back": "396 meters below sea level.", "deck": "Geography"}
        ])
    },
    {
        "text": "Python's list comprehension provides a concise way to create lists. It consists of brackets containing an expression followed by a for clause.",
        "output": json.dumps([
            {"front": "What does Python's list comprehension provide?", "back": "A concise way to create lists from expressions and loops.", "deck": "Programming/Python"},
            {"front": "What is the basic structure of a list comprehension?", "back": "Brackets with an expression, a for clause, and optional for/if clauses.", "deck": "Programming/Python"}
        ])
    },
    {
        "text": "Photosynthesis is the process by which plants use sunlight, water and carbon dioxide to create oxygen and energy in the form of sugar.",
        "output": json.dumps([
            {"front": "What is photosynthesis?", "back": "Process where plants use sunlight, water, and CO2 to create oxygen and sugar.", "deck": "Biology"},
            {"front": "Where does photosynthesis occur in plant cells?", "back": "In chloroplasts using chlorophyll.", "deck": "Biology"}
        ])
    },
    {
        "text": "The French Revolution began in 1789 and ended in the late 1790s with Napoleon Bonaparte's rise to power.",
        "output": json.dumps([
            {"front": "When did the French Revolution begin?", "back": "1789.", "deck": "History"},
            {"front": "How did the French Revolution end?", "back": "With Napoleon Bonaparte's rise to power in the late 1790s.", "deck": "History"}
        ])
    },
    {
        "text": "REST is an architectural style for distributed hypermedia systems. RESTful APIs use HTTP methods: GET for retrieval, POST for creation, PUT for updates, and DELETE for removal.",
        "output": json.dumps([
            {"front": "What is REST?", "back": "An architectural style for distributed hypermedia systems.", "deck": "CS/AI"},
            {"front": "What HTTP method is used for retrieval in RESTful APIs?", "back": "GET.", "deck": "CS/AI"}
        ])
    }
]

examples = []
for ex in training_examples:
    formatted = f"<|im_start|>system\n{SUPERMEMO_RULES}\n\n{BASIC_CARDS_PROMPT}<|im_end|>\n<|im_start|>user\nPlease create spaced repetition flashcards from the text below.\n\nPRIMARY FOCUS - Selected Text:\n{ex['text']}<|im_end|>\n<|im_start|>assistant\n{ex['output']}<|im_end|>"
    examples.append({"text": formatted})

with open("training_data_formatted.jsonl", "w", encoding="utf-8") as f:
    for ex in examples:
        f.write(json.dumps(ex, ensure_ascii=False) + "\n")

print(f"Created {len(examples)} training examples")
print("Saved to training_data_formatted.jsonl")
print("\nStarting fine-tuning...")
