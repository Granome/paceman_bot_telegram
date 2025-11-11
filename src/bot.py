import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from config import BOT_TOKEN, POLL_INTERVAL, ADMIN_ID
from aiogram.filters import StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from run_tracker import RunTracker
from paceman_api import  fetch_live_runs
from localization import localization

import keyboards
from user_config import UserManager, Language, User, UserRole

bot = Bot(token=BOT_TOKEN)

dp = Dispatcher()
user_manager = UserManager()

class UserStates(StatesGroup):
    config_mode = State() 
    tracking_mode = State() 
    

run_tracker = RunTracker(bot, user_manager)

# Update the format_split_thresholds function to support localization
def format_split_thresholds(split_thresholds: dict, language: Language) -> str:
    """Format split thresholds for display with localization"""
    if not split_thresholds:
        return localization.get_text(language, "no_splits")
    
    SPLIT_ORDER = ["Second Structure", "Blind", "Eye Spy", "End Enter"]
    
    formatted = []
    
    for split_type in SPLIT_ORDER:
        if split_type in split_thresholds:
            threshold = split_thresholds[split_type]
            localized_name = localization.get_text(language, f"split_names.{split_type}")
            
            if threshold == 0:
                threshold_text = localization.get_text(language, "not_tracking")
            else:
                minutes = threshold // 60
                seconds = threshold % 60
                threshold_text = f"Sub {minutes}:{seconds:02d}"
                
            formatted.append(f"• {localized_name}: {threshold_text}")
    
    return "\n".join(formatted)

async def ensure_user_exists(user_id: int, username: str = None, first_name: str = None, state: FSMContext = None):
    """Ensure user exists in the system, create if not"""
    if not user_manager.user_exists(user_id):
        role = UserRole.USER
        if str(user_id) == str(ADMIN_ID):
            role = UserRole.ADMIN
        
        user = user_manager.create_user(
            user_id=user_id,
            username=username,
            first_name=first_name,
            role=role,
            language=Language.ENGLISH
        )
        
        # Set initial state to config mode
        if state:
            await state.set_state(UserStates.config_mode)
        
        return user
    else:
        return user_manager.get_user(user_id)
    
async def poll_api():
    while True:
        current_runs = fetch_live_runs()
        current_world_ids = {run["worldId"] for run in current_runs}
        
        # Get all tracked world IDs across all users
        all_tracked_world_ids = user_manager.get_all_tracked_world_ids()
        
        # Process runs that are currently live
        run_data_by_world = {run["worldId"]: run for run in current_runs}
        
        # Update existing tracked runs
        for world_id in all_tracked_world_ids:
            if world_id in run_data_by_world:
                # Run is still active, update message
                run_data = run_data_by_world[world_id]
                await update_tracked_run(world_id, run_data)
            else:
                # Run has disappeared, delete message
                await handle_disappeared_run(world_id)
        
        # Process new runs for users with tracking enabled
        tracking_users = user_manager.get_tracking_users()
        for user in tracking_users:
            await process_new_runs_for_user(user, current_runs, current_world_ids)
        
        await asyncio.sleep(POLL_INTERVAL)

async def update_tracked_run(world_id: str, run_data: dict):
    """Update message for a tracked run that's still active or completed"""
    all_users = user_manager.get_all_users()
    for user in all_users:
        if world_id in user.tracked_runs:
            # Check if run is completed
            credits_event = next((e for e in run_data.get('eventList', []) if e['eventId'] == 'rsg.credits'), None)
            
            if credits_event:
                # Run is completed - update message to show completion but don't remove from tracking
                await run_tracker.update_run_message(user.user_id, world_id, run_data)
            else:
                # Run is still active - update normally
                await run_tracker.update_run_message(user.user_id, world_id, run_data)

async def handle_disappeared_run(world_id: str):
    """Handle runs that have disappeared from the API"""
    all_users = user_manager.get_all_users()
    for user in all_users:
        if world_id in user.tracked_runs:
            # Delete the message
            await run_tracker.delete_run_message(user.user_id, world_id)
            # Remove from tracking
            user_manager.remove_tracked_run(user.user_id, world_id)

async def process_new_runs_for_user(user: User, current_runs: list, current_world_ids: set):
    """Process new runs for a specific user based on their split thresholds"""
    user_tracked_worlds = set(user.tracked_runs.keys())
    untracked_runs = [run for run in current_runs if run["worldId"] not in user_tracked_worlds]
    
    for run in untracked_runs:
        if should_track_run(user, run):
            # Send initial message and track the run
            message_id = await run_tracker.send_run_message(user.user_id, run)
            if message_id:
                user_manager.add_tracked_run(user.user_id, run["worldId"], message_id)

def should_track_run(user: User, run_data: dict) -> bool:
    """Determine if a run should be tracked based on user's split thresholds using IGT"""
    split_thresholds = getattr(user, 'split_thresholds', {})
    
    # Extract all events first
    events = run_data.get('eventList', [])
    
    # Check for credits - if run is finished, we might want to track it differently
    credits_event = next((e for e in events if e['eventId'] == 'rsg.credits'), None)
    
    # Check each split type
    for split_type, threshold in split_thresholds.items():
        if threshold <= 0:  # Skip if not tracking this split
            continue
            
        if split_type == 'Second Structure':
            # For Second Structure, we need both fortress and bastion
            fortress_event = next((e for e in events if e['eventId'] == 'rsg.enter_fortress'), None)
            bastion_event = next((e for e in events if e['eventId'] == 'rsg.enter_bastion'), None)
            
            if fortress_event and bastion_event:
                # Take the later of the two events (the second structure entered)
                second_structure_time = max(fortress_event['igt'], bastion_event['igt']) / 1000
                if second_structure_time <= threshold:
                    return True
                    
        elif split_type == 'Blind':
            blind_event = next((e for e in events if e['eventId'] == 'rsg.first_portal'), None)
            if blind_event and (blind_event['igt'] / 1000) <= threshold:
                return True
                
        elif split_type == 'Eye Spy':
            stronghold_event = next((e for e in events if e['eventId'] == 'rsg.enter_stronghold'), None)
            if stronghold_event and (stronghold_event['igt'] / 1000) <= threshold:
                return True
                
        elif split_type == 'End Enter':
            end_event = next((e for e in events if e['eventId'] == 'rsg.enter_end'), None)
            if end_event and (end_event['igt'] / 1000) <= threshold:
                return True
    
    return False

def get_split_type_from_event(event_id: str) -> str:
    """Map event IDs to split types"""
    event_to_split = {
        'rsg.enter_fortress': 'Second Structure',
        'rsg.enter_bastion': 'Second Structure',  # Both map to Second Structure
        'rsg.first_portal': 'Blind',
        'rsg.enter_stronghold': 'Eye Spy',
        'rsg.enter_end': 'End Enter'
    }
    return event_to_split.get(event_id, '')


@dp.message(Command("start"))
async def start_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id

    role = UserRole.USER
    if str(user_id) == str(ADMIN_ID):
        role = UserRole.ADMIN
    
    if not user_manager.user_exists(user_id):
        user = user_manager.create_user(
            user_id=user_id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            role=role,
            language=Language.ENGLISH
        )
        await state.set_state(UserStates.config_mode)
    else:
        user = user_manager.get_user(user_id)
        if user.config.tracking_enabled:
            await state.set_state(UserStates.tracking_mode)
        else:
            await state.set_state(UserStates.config_mode)
    
    await message.answer(localization.get_text(user.language, "start"), reply_markup=keyboards.get_language_keyboard(user.language))

async def sync_user_state(user_id: int, state: FSMContext):
    """Sync FSM state with user's persistent tracking state"""
    user = user_manager.get_user(user_id)
    if user:
        if user.config.tracking_enabled:
            await state.set_state(UserStates.tracking_mode)
        else:
            await state.set_state(UserStates.config_mode)

@dp.message(Command("status"))
async def status_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    await ensure_user_exists(
        user_id=user_id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        state=state
    )
    
    # Sync state to ensure consistency
    await sync_user_state(user_id, state)
    
    user = user_manager.get_user(user_id)
    current_state = await state.get_state()
    split_thresholds = getattr(user, 'split_thresholds', {})
    
    if current_state == UserStates.tracking_mode:
        status_text = localization.get_text(user.language, "tracking_active_status") + "\n\n"
    else:
        status_text = localization.get_text(user.language, "tracking_inactive_status") + "\n\n"
    
    status_text += localization.get_text(user.language, "configured_splits") + "\n"
    if split_thresholds:
        for split_type, threshold in split_thresholds.items():
            localized_name = localization.get_text(user.language, f"split_names.{split_type}")
            if threshold > 0:
                minutes = threshold // 60
                seconds = threshold % 60
                status_text += f"• {localized_name}: Sub {minutes}:{seconds:02d}\n"
            else:
                status_text += f"• {localized_name}: " + localization.get_text(user.language, "not_tracking") + "\n"
    else:
        status_text += localization.get_text(user.language, "no_splits") + "\n"
    
    status_text += f"\n" + localization.get_text(user.language, "commands") + "\n"
    status_text += f"/start_tracking - {'(active)' if current_state == UserStates.tracking_mode else 'Start tracking'}\n"
    status_text += f"/stop_tracking - {'Stop tracking' if current_state == UserStates.tracking_mode else '(inactive)'}\n"
    status_text += f"/config - " + localization.get_text(user.language, "configure_settings") + "\n"
    
    await message.answer(status_text, parse_mode="HTML")

@dp.message(Command("start_tracking"))
async def start_tracking_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    await ensure_user_exists(
        user_id=user_id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        state=state
    )

    user = user_manager.get_user(user_id)
    split_thresholds = getattr(user, 'split_thresholds', {})
    
    if not split_thresholds or all(threshold == 0 for threshold in split_thresholds.values()):
        await message.answer(
            localization.get_text(user.language, "need_splits_first") + "\n\n" +
            localization.get_text(user.language, "use_config"),
            parse_mode="HTML"
        )
        return
    
    # Update both FSM state and persistent user config
    await state.set_state(UserStates.tracking_mode)
    user_manager.update_user_tracking_state(user_id, True)
    
    await message.answer(
        localization.get_text(user.language, "tracking_started") + "\n\n" +
        localization.get_text(user.language, "now_receiving_notifications") + "\n\n" +
        localization.get_text(user.language, "use_stop_tracking"),
        parse_mode="HTML"
    )

@dp.message(Command("stop_tracking"))
async def stop_tracking_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id

    await ensure_user_exists(
        user_id=user_id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        state=state
    )
    
    user = user_manager.get_user(user_id)
    
    # Update both FSM state and persistent user config
    await state.set_state(UserStates.config_mode)
    user_manager.update_user_tracking_state(user_id, False)
    
    await message.answer(
        localization.get_text(user.language, "tracking_stopped") + "\n\n" +
        localization.get_text(user.language, "now_back_to_config"),
        parse_mode="HTML",
        reply_markup=keyboards.get_config_menu(user.language)
    )

@dp.callback_query(lambda c: c.data in ['setEnglish', 'setUkrainian'])
async def language_handler(callback_query: CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id

    await ensure_user_exists(
        user_id=user_id,
        username=callback_query.from_user.username,
        first_name=callback_query.from_user.first_name,
        state=state
    )

    language = Language.ENGLISH if callback_query.data == "setEnglish" else Language.UKRAINIAN
    user = user_manager.get_user(user_id)
    result = user_manager.update_user_language(user_id, language)
    
    if result["success"]:
        await callback_query.message.edit_text(
            localization.get_text(language, "language_set"), 
            reply_markup=keyboards.get_language_set_menu(language)
        )

@dp.callback_query(lambda c: any(c.data.startswith(prefix) for prefix in ['fort_', 'blind_', 'strong_', 'end_']))
async def split_threshold_handler(callback_query: CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id

    await ensure_user_exists(
        user_id=user_id,
        username=callback_query.from_user.username,
        first_name=callback_query.from_user.first_name,
        state=state
    )

    user = user_manager.get_user(user_id)
    data = callback_query.data
    
    # Extract split type and threshold from callback data
    if data.startswith('fort_'):
        split_type = "Second Structure"
        threshold = data.replace('fort_', '')
    elif data.startswith('blind_'):
        split_type = "Blind"
        threshold = data.replace('blind_', '')
    elif data.startswith('strong_'):
        split_type = "Eye Spy"
        threshold = data.replace('strong_', '')
    elif data.startswith('end_'):
        split_type = "End Enter"
        threshold = data.replace('end_', '')
    else:
        return
    
    # Convert threshold to readable format
    if threshold == '0':
        threshold_text = localization.get_text(user.language, "dont_track")
    else:
        # Convert seconds to minutes:seconds format (e.g., 300 -> 3:00)
        minutes = int(threshold) // 60
        seconds = int(threshold) % 60
        threshold_text = f"Sub {minutes}:{seconds:02d}"
    
    # Update user configuration
    result = user_manager.update_user_split_threshold(user_id, split_type, threshold)
    
    if result["success"]:
        localized_split_name = localization.get_text(user.language, f"split_names.{split_type}")
        await callback_query.message.edit_text(
            localization.get_text(user.language, "split_set", split_name=localized_split_name, threshold=threshold_text) + "\n\n" +
            localization.get_text(user.language, "select_another"),
            parse_mode="HTML",
            reply_markup=keyboards.get_splits_menu(user.language)
        )
    else:
        print(result["error"])
        await callback_query.message.edit_text(
            f"❌ Failed to update {split_type} threshold. Please try again.",
            parse_mode="HTML",
            reply_markup=keyboards.get_splits_menu(user.language)
        )

@dp.callback_query(lambda c: c.data == 'displaySplits')
async def display_splits_handler(callback_query: CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id

    await ensure_user_exists(
        user_id=user_id,
        username=callback_query.from_user.username,
        first_name=callback_query.from_user.first_name,
        state=state
    )

    user = user_manager.get_user(user_id)
    

    
    # Get user's split thresholds
    split_thresholds = getattr(user, 'split_thresholds', {})
    
    if not split_thresholds:
        await callback_query.message.edit_text(
            localization.get_text(user.language, "no_thresholds_set") + "\n\n" +
            localization.get_text(user.language, "use_splits_to_follow"),
            parse_mode="HTML",
            reply_markup=keyboards.get_config_menu(user.language)
        )
        return
    
    message_text = localization.get_text(user.language, "current_thresholds") + "\n\n" + format_split_thresholds(split_thresholds, user.language)
    
    await callback_query.message.edit_text(
        message_text,
        parse_mode="HTML",
        reply_markup=keyboards.get_splits_menu(user.language)
    )

@dp.message(Command("track_run"))
async def track_run_handler(message: Message, state: FSMContext):
    """Manually track a specific run by world ID"""
    user_id = message.from_user.id
    
    await ensure_user_exists(
        user_id=user_id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        state=state
    )
    
    args = message.text.split()
    
    if len(args) < 2:
        await message.answer("Usage: /track_run <world_id>")
        return
    
    world_id = args[1]
    
    # Check if run exists in current runs
    current_runs = fetch_live_runs()
    run_data = next((run for run in current_runs if run["worldId"] == world_id), None)
    
    if not run_data:
        await message.answer("❌ Run not found or not currently active.")
        return
    
    # Track the run
    message_id = await run_tracker.send_run_message(user_id, run_data)
    if message_id:
        user_manager.add_tracked_run(user_id, world_id, message_id)
        await message.answer("✅ Run tracking started!")
    else:
        await message.answer("❌ Failed to start tracking run.")

@dp.message(Command("untrack_run"))
async def untrack_run_handler(message: Message, state: FSMContext):
    """Stop tracking a specific run"""
    user_id = message.from_user.id
    
    await ensure_user_exists(
        user_id=user_id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        state=state
    )
    
    args = message.text.split()
    
    if len(args) < 2:
        await message.answer("Usage: /untrack_run <world_id>")
        return
    
    world_id = args[1]
    
    # Delete message and remove tracking
    await run_tracker.delete_run_message(user_id, world_id)
    user_manager.remove_tracked_run(user_id, world_id)
    
    await message.answer("✅ Run tracking stopped.")

@dp.message(Command("my_tracked_runs"))
async def my_tracked_runs_handler(message: Message, state: FSMContext):
    """Show all currently tracked runs"""
    user_id = message.from_user.id
    
    await ensure_user_exists(
        user_id=user_id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        state=state
    )
    
    tracked_runs = user_manager.get_tracked_runs(user_id)
    
    if not tracked_runs:
        await message.answer("You are not tracking any runs.", parse_mode="HTML")
        return
    
    runs_list = "\n".join([f"• {world_id[:16]}..." for world_id in tracked_runs.keys()])
    await message.answer(f"<b>Your tracked runs:</b>\n\n{runs_list}", parse_mode="HTML")
    
@dp.message(Command("config"))
async def config_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    await ensure_user_exists(
        user_id=user_id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        state=state
    )
    
    current_state = await state.get_state()
    user = user_manager.get_user(user_id)
    
    if current_state == UserStates.tracking_mode:
        split_thresholds = getattr(user, 'split_thresholds', {})
        await message.answer(
            localization.get_text(user.language, "config_menu_tracking") + "\n\n" +
            localization.get_text(user.language, "now_receiving_notifications") + "\n\n" +
            "<b>" + localization.get_text(user.language, "current_splits") + "</b>\n" +
            format_split_thresholds(split_thresholds, user.language),
            parse_mode="HTML",
            reply_markup=keyboards.get_config_menu_active(user.language)
        )
    else:
        split_thresholds = getattr(user, 'split_thresholds', {})
        
        if split_thresholds and any(threshold > 0 for threshold in split_thresholds.values()):
            message_text = (localization.get_text(user.language, "config_menu") + "\n\n" +
                          "<b>" + localization.get_text(user.language, "current_splits") + "</b>\n" +
                          format_split_thresholds(split_thresholds, user.language))
        else:
            message_text = (localization.get_text(user.language, "config_menu") + "\n\n" +
                          localization.get_text(user.language, "no_splits_configured"))
        
        await message.answer(
            message_text,
            parse_mode="HTML",
            reply_markup=keyboards.get_config_menu(user.language)
        )

@dp.callback_query(lambda c: c.data == 'stop_tracking')
async def stop_tracking_callback_handler(callback_query: CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    
    await state.set_state(UserStates.config_mode)
    user_manager.update_user_tracking_state(user_id, False)
    
    user = user_manager.get_user(user_id)
    
    await callback_query.message.edit_text(
        localization.get_text(user.language, "tracking_stopped") + "\n\n" +
        localization.get_text(user.language, "now_back_to_config"),
        parse_mode="HTML",
        reply_markup=keyboards.get_config_menu(user.language)
    )

@dp.callback_query(lambda c: c.data == 'start_tracking')
async def start_tracking_callback_handler(callback_query: CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    
    await ensure_user_exists(
        user_id=user_id,
        username=callback_query.from_user.username,
        first_name=callback_query.from_user.first_name,
        state=state
    )
    
    user = user_manager.get_user(user_id)
    split_thresholds = getattr(user, 'split_thresholds', {})
    
    if not split_thresholds or all(threshold == 0 for threshold in split_thresholds.values()):
        await callback_query.answer(
            localization.get_text(user.language, "need_splits_first") + " " +
            localization.get_text(user.language, "use_splits_to_follow"),
            show_alert=True
        )
        return
    
    await state.set_state(UserStates.tracking_mode)
    user_manager.update_user_tracking_state(user_id, True)
    
    await callback_query.message.edit_text(
        localization.get_text(user.language, "tracking_started") + "\n\n" +
        localization.get_text(user.language, "now_receiving_notifications") + "\n\n" +
        "<b>" + localization.get_text(user.language, "current_thresholds") + "</b>\n" +
        format_split_thresholds(split_thresholds, user.language) + "\n\n" +
        localization.get_text(user.language, "use_stop_tracking"),
        parse_mode="HTML",
        reply_markup=keyboards.get_config_menu_active(user.language)
    )

@dp.message()
async def handle_other_messages(message: Message, state: FSMContext):
    """Handle all non-command messages"""
    user_id = message.from_user.id
    await ensure_user_exists(
        user_id=user_id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        state=state
    )

    user = user_manager.get_user(user_id)

    if message.text and message.text.startswith('/'):
        return
    
    current_state = await state.get_state()
    
    if current_state == UserStates.tracking_mode:
        await message.answer(
            localization.get_text(user.language, "currently_tracking") + "\n\n" +
            localization.get_text(user.language, "receiving_notifications") + "\n" +
            localization.get_text(user.language, "use_stop_tracking"),
            parse_mode="HTML"
        )
    else:
        await message.answer(
            localization.get_text(user.language, "please_use_commands") + "\n\n" + "/config"

        )

@dp.callback_query(lambda c: c.data == 'to_config')
async def back_to_config_handler(callback_query: CallbackQuery, state: FSMContext):
    """Handle back to configuration menu"""
    user_id = callback_query.from_user.id
    current_state = await state.get_state()
    user = user_manager.get_user(user_id)
    
    if current_state == UserStates.tracking_mode:
        # Show tracking active version
        split_thresholds = getattr(user, 'split_thresholds', {})
        await callback_query.message.edit_text(
            localization.get_text(user.language, "tracking_active_status") + "\n\n" +
            localization.get_text(user.language, "now_receiving_notifications") + "\n\n" +
            "<b>" + localization.get_text(user.language, "current_thresholds") + "</b>\n" +
            format_split_thresholds(split_thresholds, user.language),
            parse_mode="HTML",
            reply_markup=keyboards.get_config_menu_active(user.language)
        )
    else:
        # Show normal config menu
        split_thresholds = getattr(user, 'split_thresholds', {})
        if split_thresholds and any(threshold > 0 for threshold in split_thresholds.values()):
            message_text = (localization.get_text(user.language, "config_menu") + "\n\n" +
                          "<b>" + localization.get_text(user.language, "current_splits") + "</b>\n" +
                          format_split_thresholds(split_thresholds, user.language))
        else:
            message_text = (localization.get_text(user.language, "config_menu") + "\n\n" +
                          localization.get_text(user.language, "no_splits_configured"))
        
        await callback_query.message.edit_text(
            message_text,
            parse_mode="HTML",
            reply_markup=keyboards.get_config_menu(user.language)
        )

@dp.callback_query(lambda c: c.data in ['openSplitsMenu', 'OpenLanguageMenu', 'fortSplit', 'blindSplit', 'strongholdSplit', 'endSplit', 'displaySplits'])
async def config_menu_handler(callback_query: CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id

    # Auto-create user if not exists
    await ensure_user_exists(
        user_id=user_id,
        username=callback_query.from_user.username,
        first_name=callback_query.from_user.first_name,
        state=state
    )

    user = user_manager.get_user(user_id)
    current_state = await state.get_state()
    
    # Check if user is in tracking mode
    if current_state == UserStates.tracking_mode:
        await callback_query.answer(
            localization.get_text(user.language, "configuration_disabled"),
            show_alert=True
        )
        return
    
    if callback_query.data == "openSplitsMenu":
        await callback_query.message.edit_text(
            localization.get_text(user.language, "select_split"),
            parse_mode="HTML",
            reply_markup=keyboards.get_splits_menu(user.language)
        )
    
    elif callback_query.data == "OpenLanguageMenu":
        await callback_query.message.edit_text(
            localization.get_text(user.language, "start"),
            parse_mode="HTML",
            reply_markup=keyboards.get_language_keyboard(user.language)
        )
    
    elif callback_query.data == "fortSplit":
        localized_name = localization.get_text(user.language, "split_names.Second Structure")
        await callback_query.message.edit_text(
            localization.get_text(user.language, "configure_split", split_name=localized_name),
            parse_mode="HTML",
            reply_markup=keyboards.get_fort_menu(user.language)
        )
    
    elif callback_query.data == "blindSplit":
        localized_name = localization.get_text(user.language, "split_names.Blind")
        await callback_query.message.edit_text(
            localization.get_text(user.language, "configure_split", split_name=localized_name),
            parse_mode="HTML",
            reply_markup=keyboards.get_blind_menu(user.language)
        )
    
    elif callback_query.data == "strongholdSplit":
        localized_name = localization.get_text(user.language, "split_names.Eye Spy")
        await callback_query.message.edit_text(
            localization.get_text(user.language, "configure_split", split_name=localized_name),
            parse_mode="HTML",
            reply_markup=keyboards.get_strong_menu(user.language)
        )
    
    elif callback_query.data == "endSplit":
        localized_name = localization.get_text(user.language, "split_names.End Enter")
        await callback_query.message.edit_text(
            localization.get_text(user.language, "configure_split", split_name=localized_name),
            parse_mode="HTML",
            reply_markup=keyboards.get_end_menu(user.language)
        )

async def main():
    polling_task = asyncio.create_task(dp.start_polling(bot))
    api_polling_task = asyncio.create_task(poll_api())
    
    await asyncio.gather(polling_task, api_polling_task)

if __name__ == "__main__":
    asyncio.run(main())