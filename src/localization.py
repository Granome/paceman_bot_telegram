import json
import os
from typing import Dict, Any
from user_config import Language

class Localization:
    def __init__(self):
        self.locales = {}
        self.load_locales()
    
    def load_locales(self):
        """Load all locale files"""
        locales_dir = os.path.join(os.path.dirname(__file__), "..", "locales")
        for filename in os.listdir(locales_dir):
            if filename.endswith('.json'):
                lang_code = filename.split('.')[0]
                with open(os.path.join(locales_dir, filename), 'r', encoding='utf-8') as f:
                    self.locales[lang_code] = json.load(f)
    
    def get_text(self, language: Language, key: str, **kwargs) -> str:
        """Get localized text for a key"""
        lang_code = "en" if language == Language.ENGLISH else "uk"
        
        # Navigate nested keys (e.g., "split_names.Second Structure")
        keys = key.split('.')
        value = self.locales.get(lang_code, {})
        
        for k in keys:
            value = value.get(k, {})
            if not isinstance(value, dict) and k == keys[-1]:
                # Found the final value
                if isinstance(value, str) and kwargs:
                    return value.format(**kwargs)
                return value
        
        # Fallback to English if key not found
        if lang_code != "en":
            value = self.locales.get("en", {})
            for k in keys:
                value = value.get(k, {})
                if not isinstance(value, dict) and k == keys[-1]:
                    if isinstance(value, str) and kwargs:
                        return value.format(**kwargs)
                    return value
        
        return key  # Return the key itself if not found

# Create global instance
localization = Localization()