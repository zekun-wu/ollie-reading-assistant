"""
Regenerate participant JSON files (1.json to 100.json).
Each file: {"default": {"condition_order": ["assistance"|"eye_assistance", ...], "assistance": [4 images], "eye_assistance": [4 images]}}.
- 4 pairs of consecutive images; for each pair, one random image -> assistance, the other -> eye_assistance.
- Order of the 4 images in each list is randomized.
- condition_order is randomized to ["assistance","eye_assistance"] or ["eye_assistance","assistance"].
"""
import json
import random
from pathlib import Path

# Consecutive pairs from the storytelling image set (8 images = 4 per condition)
IMAGE_PAIRS = [
    ("1.jpg", "2.jpg"),
    ("3.jpg", "4.jpg"),
    ("5.jpg", "6.jpg"),
]

PARTICIPANTS_DIR = Path(__file__).parent
NUM_PARTICIPANTS = 100


def generate_one_participant():
    assistance = []
    eye_assistance = []
    for img_a, img_b in IMAGE_PAIRS:
        if random.choice([True, False]):
            assistance.append(img_a)
            eye_assistance.append(img_b)
        else:
            assistance.append(img_b)
            eye_assistance.append(img_a)
    random.shuffle(assistance)
    random.shuffle(eye_assistance)
    condition_order = ["assistance", "eye_assistance"]
    random.shuffle(condition_order)
    return {
        "default": {
            "condition_order": condition_order,
            "assistance": assistance,
            "eye_assistance": eye_assistance,
        }
    }


def main():
    for i in range(1, NUM_PARTICIPANTS + 1):
        data = generate_one_participant()
        path = PARTICIPANTS_DIR / f"{i}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Wrote {path}")
    print(f"Done. Regenerated {NUM_PARTICIPANTS} participant files.")


if __name__ == "__main__":
    main()
