import inspect
import edge_tts

try:
    print(inspect.getsource(edge_tts.Communicate))
except Exception as e:
    print(f"Error: {e}")
