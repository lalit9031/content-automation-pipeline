import sys
import os
from pathlib import Path
from unittest.mock import MagicMock

# Insert src and project root directory to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

# Mock streamlit before importing app
import sys
mock_st = MagicMock()
mock_st.session_state = {}
sys.modules["streamlit"] = mock_st

from content_pipeline.config import Settings
import app

def test_successful_run():
    print("--- Running Success Scenario ---")
    mock_st.session_state.clear()
    settings = Settings.from_environment(Path(__file__).resolve().parent.parent)
    
    # Ensure there is a valid key from .env or environment
    if not settings.gemini_api_key:
        print("Skipping success scenario: No valid GEMINI_API_KEY found.")
        return
        
    lyrics, style = app.expand_general_prompt_to_lyrics_and_style_dynamic(
        settings,
        prompt="A energetic rock song about success and victory",
        singer_gender="Male",
        language="Hindi"
    )
    
    print("Gemini API Error in state:", mock_st.session_state.get("gemini_api_error"))
    print("Returned Lyrics preview:", lyrics[:100] + "...")
    
    # Assert no error was populated
    assert "gemini_api_error" not in mock_st.session_state, "Expected no error in session state on success"
    assert "अपना सामान" not in lyrics, "Expected dynamic lyrics, but got fallback song"
    print("✅ Success scenario passed!")

def test_failure_fallback():
    print("\n--- Running Failure & Fallback Scenario ---")
    mock_st.session_state.clear()
    
    import dataclasses
    # Create setting with completely invalid key to force failure
    settings_base = Settings.from_environment(Path(__file__).resolve().parent.parent)
    settings = dataclasses.replace(
        settings_base,
        gemini_api_key="AIzaSy_this_is_an_invalid_key_to_force_failure",
        gemini_api_keys=("AIzaSy_this_is_an_invalid_key_to_force_failure",)
    )
    
    # Temporary clear env key to prevent it from succeeding using env variables
    orig_env = os.environ.get("GEMINI_API_KEY")
    if orig_env:
        del os.environ["GEMINI_API_KEY"]
        
    try:
        lyrics, style = app.expand_general_prompt_to_lyrics_and_style_dynamic(
            settings,
            prompt="A happy upbeat pop song",
            singer_gender="Female",
            language="Hindi"
        )
        
        print("Gemini API Error in state:", mock_st.session_state.get("gemini_api_error"))
        print("Returned Lyrics preview:", lyrics[:100] + "...")
        
        # Check that error is in session state
        assert "gemini_api_error" in mock_st.session_state, "Expected API error to be recorded in session state"
        # Check that it falls back to the happy song from the local offline template
        assert "सुबह की धूप में" in lyrics, "Expected happy offline template song"
        print("✅ Failure fallback scenario passed!")
    finally:
        # Restore environment variable
        if orig_env:
            os.environ["GEMINI_API_KEY"] = orig_env

def test_custom_ui_key_priority():
    print("\n--- Running Custom UI Key Priority Scenario ---")
    mock_st.session_state.clear()
    
    settings_base = Settings.from_environment(Path(__file__).resolve().parent.parent)
    valid_key = settings_base.gemini_api_key
    if not valid_key:
        print("Skipping custom UI key priority test: No valid GEMINI_API_KEY found.")
        return
        
    import dataclasses
    # Force settings keys to be invalid
    settings = dataclasses.replace(
        settings_base,
        gemini_api_key="AIzaSy_invalid_key_one",
        gemini_api_keys=("AIzaSy_invalid_key_one", "AIzaSy_invalid_key_two")
    )
    
    # Temporarily clear env key to prevent env success
    orig_env = os.environ.get("GEMINI_API_KEY")
    if orig_env:
        del os.environ["GEMINI_API_KEY"]
        
    try:
        # Put the valid key into the session state (Custom UI key)
        mock_st.session_state["custom_gemini_api_key"] = valid_key
        
        lyrics, style = app.expand_general_prompt_to_lyrics_and_style_dynamic(
            settings,
            prompt="A happy upbeat pop song about success",
            singer_gender="Female",
            language="Hindi"
        )
        
        print("Gemini API Error in state:", mock_st.session_state.get("gemini_api_error"))
        print("Returned Lyrics preview:", lyrics[:100] + "...")
        
        # Assert no error since the valid custom key prioritized at index 0 should succeed
        assert "gemini_api_error" not in mock_st.session_state, "Expected no error in session state as custom valid key should take priority and succeed"
        assert "अपना सामान" not in lyrics, "Expected dynamic lyrics from valid custom key"
        print("✅ Custom UI key priority scenario passed!")
    finally:
        if orig_env:
            os.environ["GEMINI_API_KEY"] = orig_env

if __name__ == "__main__":
    try:
        test_successful_run()
        test_failure_fallback()
        test_custom_ui_key_priority()
        print("\n🎉 ALL TESTS PASSED!")
    except Exception as err:
        import traceback
        traceback.print_exc()
        sys.exit(1)
