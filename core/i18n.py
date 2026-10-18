import os
import json
from PySide6.QtCore import QObject, Signal

class I18nManager(QObject):
    locale_changed = Signal(str)
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(I18nManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        super().__init__()
        self._initialized = True
        
        self.current_locale = "en"
        self._translations = {}
        self._load_all_locales()
        
    def _load_all_locales(self):
        # Determine locales directory based on the location of this file
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.locales_dir = os.path.join(base_dir, "locales")
        
        if not os.path.exists(self.locales_dir):
            return
            
        for filename in os.listdir(self.locales_dir):
            if filename.endswith(".json"):
                locale_code = filename[:-5]
                filepath = os.path.join(self.locales_dir, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        self._translations[locale_code] = json.load(f)
                except Exception as e:
                    print(f"Error loading locale {locale_code}: {e}")

    def t(self, key: str) -> str:
        # Try current locale
        if self.current_locale in self._translations and key in self._translations[self.current_locale]:
            return self._translations[self.current_locale][key]
            
        # Try fallback (English)
        if "en" in self._translations and key in self._translations["en"]:
            return self._translations["en"][key]
            
        # Fallback to key itself
        return key

    def set_locale(self, locale_code: str):
        if locale_code != self.current_locale and locale_code in self._translations:
            self.current_locale = locale_code
            self.locale_changed.emit(self.current_locale)

    def get_available_locales(self) -> list:
        return list(self._translations.keys())

# Create the singleton instance
i18n = I18nManager()
