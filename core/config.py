import json
import os

class Config:
    def __init__(self):
        self.config_path = os.path.expanduser("~/.nyaa-desktop/config.json")
        self.default_config = {
            "download_path": os.path.expanduser("~/Downloads"),
            "theme": "dark",
            "max_concurrent_downloads": 3
        }
        self.load_config()
    
    def load_config(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                self.config = json.load(f)
        else:
            self.config = self.default_config.copy()
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            self.save_config()
    
    def save_config(self):
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=4)