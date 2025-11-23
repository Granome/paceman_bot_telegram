from aiogram import Bot
from user_config import UserManager
from aiogram.types import LinkPreviewOptions
import time
from localization import localization
from user_config import Language

class RunTracker:
    def __init__(self, bot: Bot, user_manager: UserManager):
        self.bot = bot
        self.user_manager = user_manager
        self.last_event_hashes = {}  # This is in RunTracker
    
    async def send_run_message(self, user_id: int, run_data: dict) -> int:
        """Send a run message and return message ID"""
        user = self.user_manager.get_user(user_id)
        language = user.language if user else Language.ENGLISH
        
        message_text = self._format_run_message(run_data, language)
        
        try:
            message = await self.bot.send_message(user_id, message_text, parse_mode="HTML", link_preview_options=LinkPreviewOptions(is_disabled=True))
            
            # Initialize the hash cache when we first send a message
            cache_key = (user_id, run_data['worldId'])
            self.last_event_hashes[cache_key] = self._get_events_hash(run_data)
            
            return message.message_id
        except Exception as e:
            print(f"Error sending message to user {user_id}: {e}")
            return None
    
    async def update_run_message(self, user_id: int, world_id: str, run_data: dict) -> bool:
        """Update message only if events actually changed"""
        tracked_runs = self.user_manager.get_tracked_runs(user_id)
        if world_id not in tracked_runs or not tracked_runs[world_id].message_id:
            return False
        
        user = self.user_manager.get_user(user_id)
        language = user.language if user else Language.ENGLISH
        
        message_id = tracked_runs[world_id].message_id
        current_events_hash = self._get_events_hash(run_data)
        
        # Check if events actually changed
        cache_key = (user_id, world_id)
        
        if cache_key in self.last_event_hashes and self.last_event_hashes[cache_key] == current_events_hash:
            return True  # No actual changes, no update needed
        
        message_text = self._format_run_message(run_data, language)
        
        try:
            await self.bot.edit_message_text(
                chat_id=user_id,
                message_id=message_id,
                text=message_text,
                parse_mode="HTML",
                link_preview_options=LinkPreviewOptions(is_disabled=True)
            )
            # Update the events hash
            self.last_event_hashes[cache_key] = current_events_hash
            return True
        except Exception as e:
            if "message is not modified" in str(e):
                # This means our hash cache missed something, but it's not critical
                # Update the cache and continue
                self.last_event_hashes[cache_key] = current_events_hash
                return True
            print(f"Error updating message for user {user_id}, run {world_id}: {e}")
            return False
    
    async def delete_run_message(self, user_id: int, world_id: str) -> bool:
        """Delete a run message"""
        tracked_runs = self.user_manager.get_tracked_runs(user_id)
        if world_id not in tracked_runs or not tracked_runs[world_id].message_id:
            return False
        
        message_id = tracked_runs[world_id].message_id
        
        # Clean up cache
        cache_key = (user_id, world_id)
        if cache_key in self.last_event_hashes:
            del self.last_event_hashes[cache_key]
        
        # try:
        #     await self.bot.delete_message(
        #         chat_id=user_id,
        #         message_id=message_id
        #     )
        #     return True
        # except Exception as e:
        #     print(f"Error deleting message for user {user_id}, run {world_id}: {e}")
        #     return False
    
    def _format_run_message(self, run_data: dict, language: Language) -> str:
        """Format run data into a readable message with IGT times"""
        events = run_data.get('eventList', [])
        
        # Check if run is completed
        credits_event = next((e for e in events if e['eventId'] == 'rsg.credits'), None)
        completed = credits_event is not None

        nickname = run_data.get('nickname', localization.get_text(language, "unknown_player"))
        live_account = run_data['user'].get('liveAccount')
        world_id = run_data["worldId"]
        
        # Extract item counts
        pearl_count = 0
        rod_count = 0
        if 'itemData' in run_data and 'estimatedCounts' in run_data['itemData']:
            estimated_counts = run_data['itemData']['estimatedCounts']
            pearl_count = estimated_counts.get('minecraft:ender_pearl', 0)
            rod_count = estimated_counts.get('minecraft:blaze_rod', 0)
        
        # Build display text for each milestone
        milestone_texts = []
        
        # Second Structure (show both times and the max)
        fortress = next((e for e in events if e['eventId'] == 'rsg.enter_fortress'), None)
        bastion = next((e for e in events if e['eventId'] == 'rsg.enter_bastion'), None)
        if fortress and bastion:
            fortress_name = localization.get_text(language, "split_names.Fortress")
            bastion_name = localization.get_text(language, "split_names.Bastion")
            
            if fortress['igt'] >= bastion['igt']: 
                milestone_texts.append(f"• {bastion_name}: {format_igt_time(bastion['igt']/1000)}")
                milestone_texts.append(f"• {fortress_name}: {format_igt_time(fortress['igt']/1000)}")
            else: 
                milestone_texts.append(f"• {fortress_name}: {format_igt_time(fortress['igt']/1000)}")
                milestone_texts.append(f"• {bastion_name}: {format_igt_time(bastion['igt']/1000)}")            
        
        # Other milestones
        event_mapping = [
            ('rsg.first_portal', 'split_names.Blind'),
            ('rsg.enter_stronghold', 'split_names.Eye Spy'), 
            ('rsg.enter_end', 'split_names.End Enter')
        ]
        
        for event_name, split_key in event_mapping:
            event = next((e for e in events if e['eventId'] == event_name), None)
            if event:
                display_name = localization.get_text(language, split_key)
                milestone_texts.append(f"• {display_name}: {format_igt_time(event['igt']/1000)}")
        
        # Add credits if completed
        if credits_event:
            completed_text = localization.get_text(language, "completed_run")
            milestone_texts.append(f"\n\n✅ <b>{completed_text}</b>: {format_igt_time(credits_event['igt']/1000)}")
        
        status_emoji = "✅" if completed else "🏃‍♂️"

        # Format player name - either as bold text or bold link
        if live_account:
            # For HTML, we can't easily make links bold in Telegram
            # Either use just the link or use bold text without link
            player_name = f'<a href="https://twitch.tv/{live_account}">{nickname}</a>'
        else:
            player_name = f'<b>{nickname}</b>'
        
        # Add item counts to the header
        item_info = ""
        if (pearl_count > 0 or rod_count > 0) and not completed:
            pearls_text = localization.get_text(language, "pearls")
            rods_text = localization.get_text(language, "rods")
            item_info = f"{pearls_text} 🔮 : {pearl_count} | {rods_text} 🪄: {rod_count}\n"
        
        splits_text = localization.get_text(language, "splits_link")
        game_version = run_data.get('gameVersion', localization.get_text(language, "unknown_version"))
        
        events_text = "\n".join(milestone_texts) if milestone_texts else localization.get_text(language, "no_milestones")
        
        return (
            "=============================\n"
            f"{status_emoji} {player_name}\n"
            f"{game_version}\n"
            f"{item_info}\n"
            f'<a href="https://paceman.gg/stats/run/{world_id}">{splits_text}</a>\n{events_text}\n'
            "============================="
        )
                
    def _get_events_hash(self, run_data: dict) -> str:
        """Create a hash of the milestone events and item counts to detect actual changes"""
        # Only hash the milestone events we care about
        milestone_events = [
            (e['eventId'], e['igt']) 
            for e in run_data.get('eventList', []) 
            if e['eventId'] in ['rsg.enter_fortress', 'rsg.enter_bastion', 'rsg.first_portal', 'rsg.enter_stronghold', 'rsg.enter_end']
        ]
        
        # Extract item counts for hashing
        pearl_count = 0
        rod_count = 0
        if 'itemData' in run_data and 'estimatedCounts' in run_data['itemData']:
            estimated_counts = run_data['itemData']['estimatedCounts']
            pearl_count = estimated_counts.get('minecraft:ender_pearl', 0)
            rod_count = estimated_counts.get('minecraft:blaze_rod', 0)
        
        # Create a tuple with both events and item counts for hashing
        hash_data = (
            tuple(milestone_events),  # Events data
            pearl_count,              # Pearl count
            rod_count                 # Rod count
        )
        
        return str(hash(hash_data))

def format_igt_time(igt_seconds: float) -> str:
    """Convert IGT seconds to minutes:seconds format"""
    minutes = int(igt_seconds) // 60
    seconds = int(igt_seconds) % 60
    return f"{minutes}:{seconds:02d}"