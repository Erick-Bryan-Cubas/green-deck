"""
Test script for fine-tuned flashcard model
Validates JSON output and SuperMemo compliance
"""

import httpx
import json
import asyncio
from ollama.fine_tuning.prompts import SUPERMEMO_RULES, BASIC_CARDS_PROMPT

# Test texts
TEST_CASES = [
    {
        "name": "Simple Concept",
        "text": "Python is a high-level, interpreted programming language known for its simplicity and readability.",
        "expected_cards": 1
    },
    {
        "name": "Multiple Concepts",
        "text": """The HTTP protocol uses several methods: GET retrieves data, POST submits data, 
        PUT updates data, and DELETE removes data. Each method has specific use cases.""",
        "expected_cards": 4
    },
    {
        "name": "Complex Topic",
        "text": """Quantum entanglement is a physical phenomenon where pairs of particles interact 
        in such a way that the quantum state of each particle cannot be described independently. 
        This was famously called "spooky action at a distance" by Einstein.""",
        "expected_cards": 2
    }
]

async def test_model(model_name: str = "flashcard-qwen3:4b", ollama_url: str = "http://localhost:11434/api/generate"):
    """Test the fine-tuned model"""
    
    print(f"🧪 Testing model: {model_name}\n")
    
    system_prompt = f"{SUPERMEMO_RULES}\n\n{BASIC_CARDS_PROMPT}"
    
    results = {
        "total_tests": len(TEST_CASES),
        "passed": 0,
        "failed": 0,
        "details": []
    }
    
    for i, test_case in enumerate(TEST_CASES, 1):
        print(f"Test {i}/{len(TEST_CASES)}: {test_case['name']}")
        print(f"Text: {test_case['text'][:80]}...")
        
        prompt = f"""Please create spaced repetition flashcards from the text below.

PRIMARY FOCUS - Selected Text:
{test_case['text']}"""
        
        full_prompt = f"{system_prompt}\n\n{prompt}"
        
        try:
            # Call Ollama
            async with httpx.AsyncClient(timeout=60.0) as client:
                response_text = ""
                async with client.stream(
                    "POST",
                    ollama_url,
                    json={
                        "model": model_name,
                        "prompt": full_prompt,
                        "stream": True,
                        "options": {
                            "temperature": 0.2,
                            "top_p": 0.5,
                            "repeat_penalty": 1.1
                        }
                    }
                ) as response:
                    async for line in response.aiter_lines():
                        if line.strip():
                            data = json.loads(line)
                            if data.get("response"):
                                response_text += data["response"]
            
            # Try to parse JSON
            cards = None
            try:
                cards = json.loads(response_text)
            except:
                # Try to extract JSON
                import re
                match = re.search(r'\[[\s\S]*?\]', response_text)
                if match:
                    cards = json.loads(match.group(0))
            
            # Validate
            if cards is None:
                print("❌ FAILED: No valid JSON found")
                results["failed"] += 1
                results["details"].append({
                    "test": test_case["name"],
                    "status": "failed",
                    "error": "No valid JSON",
                    "response": response_text[:200]
                })
            elif not isinstance(cards, list):
                print("❌ FAILED: Output is not a JSON array")
                results["failed"] += 1
                results["details"].append({
                    "test": test_case["name"],
                    "status": "failed",
                    "error": "Not a JSON array",
                    "response": response_text[:200]
                })
            elif len(cards) == 0:
                print("❌ FAILED: Empty card array")
                results["failed"] += 1
                results["details"].append({
                    "test": test_case["name"],
                    "status": "failed",
                    "error": "Empty array",
                    "response": response_text[:200]
                })
            else:
                # Validate card structure
                valid_cards = 0
                for card in cards:
                    if "front" in card and "back" in card and "deck" in card:
                        valid_cards += 1
                
                if valid_cards == len(cards):
                    print(f"✅ PASSED: Generated {len(cards)} valid cards")
                    results["passed"] += 1
                    results["details"].append({
                        "test": test_case["name"],
                        "status": "passed",
                        "cards_generated": len(cards),
                        "sample_card": cards[0]
                    })
                    
                    # Show sample card
                    print(f"   Sample: {cards[0]['front'][:60]}...")
                else:
                    print(f"❌ FAILED: {valid_cards}/{len(cards)} cards have valid structure")
                    results["failed"] += 1
                    results["details"].append({
                        "test": test_case["name"],
                        "status": "failed",
                        "error": f"Invalid card structure: {valid_cards}/{len(cards)}",
                        "cards": cards
                    })
            
        except Exception as e:
            print(f"❌ FAILED: {str(e)}")
            results["failed"] += 1
            results["details"].append({
                "test": test_case["name"],
                "status": "failed",
                "error": str(e)
            })
        
        print()
    
    # Summary
    print("=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    print(f"Total Tests: {results['total_tests']}")
    print(f"Passed: {results['passed']} ✅")
    print(f"Failed: {results['failed']} ❌")
    print(f"Success Rate: {results['passed']/results['total_tests']*100:.1f}%")
    print()
    
    # Save results
    with open("test_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("📁 Detailed results saved to test_results.json")
    
    return results

async def compare_models(base_model: str = "qwen3:4b-instruct-q4_k_m", 
                        finetuned_model: str = "flashcard-qwen3:4b"):
    """Compare base model vs fine-tuned model"""
    
    print("🔬 COMPARING MODELS\n")
    
    print("Testing BASE model...")
    base_results = await test_model(base_model)
    
    print("\n" + "="*60 + "\n")
    
    print("Testing FINE-TUNED model...")
    finetuned_results = await test_model(finetuned_model)
    
    print("\n" + "="*60)
    print("📈 COMPARISON")
    print("="*60)
    print(f"Base Model Success Rate: {base_results['passed']/base_results['total_tests']*100:.1f}%")
    print(f"Fine-tuned Model Success Rate: {finetuned_results['passed']/finetuned_results['total_tests']*100:.1f}%")
    
    improvement = finetuned_results['passed'] - base_results['passed']
    if improvement > 0:
        print(f"\n✨ Improvement: +{improvement} tests passed")
    elif improvement < 0:
        print(f"\n⚠️  Regression: {improvement} tests passed")
    else:
        print(f"\n➡️  No change in test results")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "compare":
            # Compare base vs fine-tuned
            asyncio.run(compare_models())
        else:
            # Test specific model
            asyncio.run(test_model(sys.argv[1]))
    else:
        # Test fine-tuned model only
        asyncio.run(test_model())
