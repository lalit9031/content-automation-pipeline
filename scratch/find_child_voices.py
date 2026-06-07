import asyncio
import edge_tts

async def main():
    voices = await edge_tts.list_voices()
    print("Searching for kid, child, boy, or girl voices globally...")
    count = 0
    for v in voices:
        name = v["ShortName"]
        gender = v["Gender"]
        locale = v["Locale"]
        # Search for common indicators of child voices in Microsoft naming conventions
        name_lower = name.lower()
        if "child" in name_lower or "kid" in name_lower or "boy" in name_lower or "girl" in name_lower or "toddler" in name_lower or "baby" in name_lower:
            print(f"Name: {name}, Gender: {gender}, Locale: {locale}")
            count += 1
            
    print(f"\nTotal child-like candidates found: {count}")
    
    # Also list all en-US and en-GB voices just to check their names for common child models
    print("\n--- en-US and en-GB voices for inspection ---")
    for v in voices:
        name = v["ShortName"]
        if name.startswith("en-US-") or name.startswith("en-GB-"):
            print(f"Name: {name}, Gender: {v['Gender']}")

if __name__ == "__main__":
    asyncio.run(main())
