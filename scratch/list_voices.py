import asyncio
import edge_tts

async def main():
    voices = await edge_tts.list_voices()
    print("Available Indian voices:")
    for v in sorted(voices, key=lambda x: x["ShortName"]):
        name = v["ShortName"]
        if "-IN-" in name:
            print(f"Name: {name}, Gender: {v['Gender']}, Locale: {v['Locale']}")

if __name__ == "__main__":
    asyncio.run(main())
