import json
import os

class ConfigManager:
    DEFAULT_CONFIG = {
        "active_profile_id": 0,
        "profiles": [
            {
                "name": "Default User",
                "ram": 4096,
                "cpu_cores": 4,
                "storage_gb": 16,
                "custom_isos": [],
                "perf_mode": "Balanced",
                "resolution": "1280x720",
                "installed_games": [],
                "projects_dir": "",
                "auto_sync": True,
                "preferred_engine": "Auto"
            }
        ],
        "dark_mode": True
    }
    CONFIG_FILE = "config.json"

    @staticmethod
    def load():
        if os.path.exists(ConfigManager.CONFIG_FILE):
            try:
                with open(ConfigManager.CONFIG_FILE, "r") as f:
                    config = json.load(f)
                
                # Migration logic: If "profiles" key is missing, convert v1.x config to v2.0
                if "profiles" not in config:
                    new_config = json.loads(json.dumps(ConfigManager.DEFAULT_CONFIG))
                    profile = new_config["profiles"][0]
                    
                    # Transfer old settings into the default profile
                    profile["ram"] = config.get("ram", profile["ram"])
                    profile["cpu_cores"] = config.get("cpu_cores", profile["cpu_cores"])
                    profile["storage_gb"] = config.get("storage_gb", profile["storage_gb"])
                    profile["custom_isos"] = config.get("custom_isos", [])
                    new_config["dark_mode"] = config.get("dark_mode", True)
                    
                    # Save the migrated configuration immediately
                    ConfigManager.save(new_config)
                    return new_config
                
                return config
            except (json.JSONDecodeError, KeyError):
                return ConfigManager.DEFAULT_CONFIG
        return ConfigManager.DEFAULT_CONFIG

    @staticmethod
    def save(config):
        with open(ConfigManager.CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)
