import json
from typing import Dict, Any
import os
import time
import config

import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
import os
from enum import Enum

class Language(str, Enum):
    ENGLISH = "en"
    UKRAINIAN = "ua"

class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"

@dataclass
class TrackedRun:
    """Data class for tracking a specific run"""
    world_id: str
    message_id: int = None
    last_updated: float = None
    is_active: bool = True


@dataclass
class UserConfig:
    """User configuration settings"""
    tracking_enabled: bool = False 

@dataclass
class User:
    """User model representing a bot user"""
    user_id: int
    language: Language = Language.ENGLISH
    role: UserRole = UserRole.USER
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    config: UserConfig = None
    split_thresholds: Dict[str, int] = None
    tracked_runs: Dict[str, TrackedRun] = None  # world_id -> TrackedRun
    
    def __post_init__(self):
        if self.config is None:
            self.config = UserConfig()
        elif isinstance(self.config, dict):
            self.config = UserConfig(**self.config)
        
        if self.split_thresholds is None:
            self.split_thresholds = {}
            
        if self.tracked_runs is None:
            self.tracked_runs = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert User object to dictionary"""
        data = asdict(self)
        data['config'] = asdict(self.config)
        # Convert TrackedRun objects to dict
        data['tracked_runs'] = {world_id: asdict(tracked_run) for world_id, tracked_run in self.tracked_runs.items()}
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'User':
        """Create User object from dictionary"""
        config_data = data.pop('config', {})
        split_thresholds = data.pop('split_thresholds', {})
        tracked_runs_data = data.pop('tracked_runs', {})
        
        user = cls(**data)
        user.config = UserConfig(**config_data)
        user.split_thresholds = split_thresholds
        user.tracked_runs = {world_id: TrackedRun(**tracked_run_data) for world_id, tracked_run_data in tracked_runs_data.items()}
        return user

class UserManager:
    """Manager for handling user operations"""
    
    def __init__(self, config_file: str = "users.json"):
        self.config_file = os.path.join(config.USERS_FILE_PATH, config_file)
        self._ensure_config_file()
    
    def _ensure_config_file(self) -> None:
        """Ensure config file exists"""
        if not os.path.exists(self.config_file):
            with open(self.config_file, 'w', encoding='utf-8') as file:
                json.dump([], file, indent=4, ensure_ascii=False)
    
    def _load_users(self) -> List[Dict[str, Any]]:
        """Load all users from JSON file"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as file:
                return json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            return []
    
    def _save_users(self, users_data: List[Dict[str, Any]]) -> bool:
        """Save users to JSON file"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as file:
                json.dump(users_data, file, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Error saving users: {e}")
            return False
        
    def update_user_tracking_state(self, user_id: int, tracking_enabled: bool) -> Dict[str, Any]:
        """Update user tracking state"""
        return self.update_user_config(user_id, tracking_enabled=tracking_enabled)

    def get_tracking_users(self) -> List[User]:
        """Get all users who have tracking enabled"""
        all_users = self.get_all_users()
        return [user for user in all_users if user.config.tracking_enabled]
    
    def add_user(self, user: User) -> Dict[str, Any]:
        """
        Add a new user to the JSON file.
        
        Returns:
            dict: Operation result with success status and message
        """
        try:
            users_data = self._load_users()
            
            # Check if user already exists
            if any(user_data.get('user_id') == user.user_id for user_data in users_data):
                return {
                    "success": False,
                    "message": f"User {user.user_id} already exists",
                    "action": "exists"
                }
            
            # Add new user
            users_data.append(user.to_dict())
            
            if self._save_users(users_data):
                return {
                    "success": True,
                    "message": f"User {user.user_id} added successfully",
                    "action": "added",
                    "user": user.to_dict()
                }
            else:
                return {
                    "success": False,
                    "message": "Failed to save user data",
                    "action": "error"
                }
                
        except Exception as e:
            return {
                "success": False,
                "message": f"Error adding user: {e}",
                "action": "error"
            }
    
    def create_user(self, 
                   user_id: int, 
                   language: Language = Language.ENGLISH,
                   role: UserRole = UserRole.USER,
                   username: Optional[str] = None,
                   first_name: Optional[str] = None,
                   last_name: Optional[str] = None,
                   config: Optional[UserConfig] = None) -> Dict[str, Any]:
        """Convenience method to create and add a user"""
        user = User(
            user_id=user_id,
            language=language,
            role=role,
            username=username,
            first_name=first_name,
            last_name=last_name,
            config=config
        )
        return self.add_user(user)
    
    def get_user(self, user_id: int) -> Optional[User]:
        """Get user by ID"""
        users_data = self._load_users()
        user_data = next((u for u in users_data if u.get('user_id') == user_id), None)
        return User.from_dict(user_data) if user_data else None
    
    def user_exists(self, user_id: int) -> bool:
        """Check if user exists"""
        return self.get_user(user_id) is not None
    
    def get_all_users(self) -> List[User]:
        """Get all users"""
        users_data = self._load_users()
        return [User.from_dict(user_data) for user_data in users_data]
    
    def update_user(self, user_id: int, **kwargs) -> Dict[str, Any]:
        """
        Update user properties
        
        Args:
            user_id: User ID to update
            **kwargs: User properties to update
        
        Returns:
            dict: Operation result
        """
        try:
            users_data = self._load_users()
            
            for user_data in users_data:
                if user_data.get('user_id') == user_id:
                    # Update user properties
                    for key, value in kwargs.items():
                        if key == 'config' and isinstance(value, UserConfig):
                            user_data[key] = asdict(value)
                        else:
                            user_data[key] = value
                    
                    if self._save_users(users_data):
                        return {
                            "success": True,
                            "message": f"User {user_id} updated successfully",
                            "action": "updated"
                        }
                    else:
                        return {
                            "success": False,
                            "message": "Failed to save updated user data",
                            "action": "error"
                        }
            
            return {
                "success": False,
                "message": f"User {user_id} not found",
                "action": "not_found"
            }
            
        except Exception as e:
            return {
                "success": False,
                "message": f"Error updating user: {e}",
                "action": "error"
            }
    
    def update_user_language(self, user_id: int, language: Language) -> Dict[str, Any]:
        """Update user language"""
        return self.update_user(user_id, language=language)
    
    def update_user_config(self, user_id: int, **config_kwargs) -> Dict[str, Any]:
        """Update user configuration"""
        user = self.get_user(user_id)
        if not user:
            return {
                "success": False,
                "message": f"User {user_id} not found",
                "action": "not_found"
            }
        
        # Update config properties
        for key, value in config_kwargs.items():
            if hasattr(user.config, key):
                setattr(user.config, key, value)
        
        return self.update_user(user_id, config=user.config)
    
    def update_user_split_threshold(self, user_id: int, split_type: str, threshold: str) -> Dict[str, Any]:
        """Update user split threshold configuration"""
        try:
            users_data = self._load_users()
            user_found = False
            
            for user_data in users_data:
                if user_data.get('user_id') == user_id:
                    user_found = True
                    
                    # Initialize split_thresholds if it doesn't exist
                    if 'split_thresholds' not in user_data:
                        user_data['split_thresholds'] = {}
                    
                    # Convert threshold to integer (0 means don't track)
                    threshold_value = int(threshold) if threshold != '0' else 0
                    
                    # Update the threshold for the specific split type
                    user_data['split_thresholds'][split_type] = threshold_value
                    
                    break
            
            if not user_found:
                return {
                    "success": False, 
                    "error": "User not found",
                    "message": f"User {user_id} not found"
                }
            
            # Save updated users data
            if self._save_users(users_data):
                return {
                    "success": True, 
                    "message": f"{split_type} threshold updated to {threshold_value} seconds"
                }
            else:
                return {
                    "success": False, 
                    "error": "Save failed",
                    "message": "Failed to save user configuration"
                }
                
        except Exception as e:
            return {
                "success": False, 
                "error": str(e),
                "message": f"Error updating split threshold: {e}"
            }
            
    def get_user_split_thresholds(self, user_id: int) -> Dict[str, int]:
        """Get user's split thresholds"""
        user = self.get_user(user_id)
        if user:
            return getattr(user, 'split_thresholds', {})
        return {}
    
    def delete_user(self, user_id: int) -> Dict[str, Any]:
        """Delete user by ID"""
        try:
            users_data = self._load_users()
            initial_count = len(users_data)
            
            users_data = [u for u in users_data if u.get('user_id') != user_id]
            
            if len(users_data) < initial_count:
                if self._save_users(users_data):
                    return {
                        "success": True,
                        "message": f"User {user_id} deleted successfully",
                        "action": "deleted"
                    }
                else:
                    return {
                        "success": False,
                        "message": "Failed to save user data after deletion",
                        "action": "error"
                    }
            else:
                return {
                    "success": False,
                    "message": f"User {user_id} not found",
                    "action": "not_found"
                }
                
        except Exception as e:
            return {
                "success": False,
                "message": f"Error deleting user: {e}",
                "action": "error"
            }
        
    def add_tracked_run(self, user_id: int, world_id: str, message_id: int = None) -> Dict[str, Any]:
        """Add a run to user's tracked runs"""
        user = self.get_user(user_id)
        if not user:
            return {"success": False, "error": "User not found"}
        
        user.tracked_runs[world_id] = TrackedRun(
            world_id=world_id,
            message_id=message_id,
            last_updated=time.time(),
            is_active=True
        )
        
        
        return self._save_user(user)
    
    def update_tracked_run_message(self, user_id: int, world_id: str, message_id: int) -> Dict[str, Any]:
        """Update message ID for a tracked run"""
        user = self.get_user(user_id)
        if not user:
            return {"success": False, "error": "User not found"}
        
        if world_id not in user.tracked_runs:
            return {"success": False, "error": "Run not tracked"}
        
        user.tracked_runs[world_id].message_id = message_id
        user.tracked_runs[world_id].last_updated = time.time()
        
        return self._save_user(user)
    
    def remove_tracked_run(self, user_id: int, world_id: str) -> Dict[str, Any]:
        """Remove a run from user's tracked runs"""
        user = self.get_user(user_id)
        if not user:
            return {"success": False, "error": "User not found"}
        
        if world_id in user.tracked_runs:
            del user.tracked_runs[world_id]
        

        
        return self._save_user(user)    
    def get_tracked_runs(self, user_id: int) -> Dict[str, TrackedRun]:
        """Get all tracked runs for a user"""
        user = self.get_user(user_id)
        if user:
            return user.tracked_runs
        return {}
    
    def get_all_tracked_world_ids(self) -> List[str]:
        """Get all world IDs being tracked by any user"""
        all_users = self.get_all_users()
        world_ids = set()
        for user in all_users:
            world_ids.update(user.tracked_runs.keys())
        return list(world_ids)
    
    def _save_user(self, user: User) -> Dict[str, Any]:
        """Helper method to save a single user"""
        users_data = self._load_users()
        
        for i, user_data in enumerate(users_data):
            if user_data.get('user_id') == user.user_id:
                users_data[i] = user.to_dict()
                if self._save_users(users_data):
                    return {"success": True, "message": "User updated successfully"}
                else:
                    return {"success": False, "error": "Failed to save user data"}
        
        return {"success": False, "error": "User not found in data"}






