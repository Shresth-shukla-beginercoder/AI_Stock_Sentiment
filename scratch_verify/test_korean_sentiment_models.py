"""Test Korean sentiment models to find one with compatible label output."""
import os
import sys

# Add backend to path
sys.path.insert(0, r"C:\Users\shres\OneDrive\Desktop\AI - Stock_Sentiment -Agent\backend")

os.environ["HF_HOME"] = "/tmp/hf_test"

from transformers import pipeline

# Candidate Korean sentiment models from HuggingFace
candidates = [
    "hun3359/klue-bert-base-sentiment",  # KLUE-BERT fine-tuned on sentiment
    "matthewburke/korean_sentiment",      # Korean sentiment (binary)
    "fabriceyhc/bert-base-multilingual-cased-sentiments-student",  # multilingual
]

korean_text = "삼성전자 주가가 상승했습니다"  # "Samsung Electronics stock price rose"

for model_id in candidates:
    print(f"\n{'='*60}")
    print(f"Testing: {model_id}")
    print('='*60)
    try:
        pipe = pipeline("sentiment-analysis", model=model_id, device=-1, max_length=512, truncation=True)
        result = pipe(korean_text, return_all_scores=True, top_k=None)
        print(f"SUCCESS")
        print(f"  Input: {korean_text}")
        print(f"  Result: {result}")

        # Check if it has 3-class output (positive/neutral/negative)
        first = result[0] if isinstance(result[0], list) else result
        labels = [item['label'].lower() for item in first]
        print(f"  Labels: {labels}")

        if all(lbl in labels for lbl in ['positive', 'neutral', 'negative']):
            print("  ✓ 3-class compatible (positive/neutral/negative)")
        elif all(lbl in labels for lbl in ['positive', 'negative']):
            print("  ✓ 2-class (positive/negative) - could map neutral as 50/50")
        else:
            print(f"  ✗ Incompatible labels: {labels}")

    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {str(e)[:200]}")

print("\n\nDONE")
