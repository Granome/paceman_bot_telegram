import asyncio
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from config import BOT_TOKEN, POLL_INTERVAL, ADMIN_ID
from aiogram.filters import StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile

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
        
        if state:
            await state.set_state(UserStates.config_mode)
        
        return user
    else:
        return user_manager.get_user(user_id)
    
async def poll_api():
    while True:
        current_runs = fetch_live_runs()
        current_world_ids = {run["worldId"] for run in current_runs}
        
        all_tracked_world_ids = user_manager.get_all_tracked_world_ids()
        run_data_by_world = {run["worldId"]: run for run in current_runs}
        
        for world_id in all_tracked_world_ids:
            if world_id in run_data_by_world:
                run_data = run_data_by_world[world_id]
                await update_tracked_run(world_id, run_data)
            else:
                await handle_disappeared_run(world_id)
        
        tracking_users = user_manager.get_tracking_users()
        for user in tracking_users:
            await process_new_runs_for_user(user, current_runs, current_world_ids)
        
        await asyncio.sleep(POLL_INTERVAL)

async def update_tracked_run(world_id: str, run_data: dict):
    all_users = user_manager.get_all_users()
    for user in all_users:
        if world_id in user.tracked_runs:
            credits_event = next((e for e in run_data.get('eventList', []) if e['eventId'] == 'rsg.credits'), None)
            await run_tracker.update_run_message(user.user_id, world_id, run_data)

async def handle_disappeared_run(world_id: str):
    all_users = user_manager.get_all_users()
    for user in all_users:
        if world_id in user.tracked_runs:
            await run_tracker.delete_run_message(user.user_id, world_id)
            user_manager.remove_tracked_run(user.user_id, world_id)

async def process_new_runs_for_user(user: User, current_runs: list, current_world_ids: set):
    user_tracked_worlds = set(user.tracked_runs.keys())
    untracked_runs = [run for run in current_runs if run["worldId"] not in user_tracked_worlds]
    
    for run in untracked_runs:
        if should_track_run(user, run):
            message_id = await run_tracker.send_run_message(user.user_id, run)
            if message_id:
                user_manager.add_tracked_run(user.user_id, run["worldId"], message_id)

def should_track_run(user: User, run_data: dict) -> bool:
    split_thresholds = getattr(user, 'split_thresholds', {})
    events = run_data.get('eventList', [])
    
    for split_type, threshold in split_thresholds.items():
        if threshold <= 0:
            continue
            
        if split_type == 'Second Structure':
            fortress_event = next((e for e in events if e['eventId'] == 'rsg.enter_fortress'), None)
            bastion_event = next((e for e in events if e['eventId'] == 'rsg.enter_bastion'), None)
            if fortress_event and bastion_event:
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
            
    user = user_manager.get_user(user_id)
    await message.answer(localization.get_text(user.language, "start"), reply_markup=keyboards.get_language_keyboard(user.language))

async def sync_user_state(user_id: int, state: FSMContext):
    user = user_manager.get_user(user_id)
    if user:
        if user.config.tracking_enabled:
            await state.set_state(UserStates.tracking_mode)
        else:
            await state.set_state(UserStates.config_mode)

@dp.message(Command("status"))
async def status_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    await ensure_user_exists(user_id, message.from_user.username, message.from_user.first_name, state)
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
    
    await ensure_user_exists(user_id, message.from_user.username, message.from_user.first_name, state)
    user = user_manager.get_user(user_id)
    split_thresholds = getattr(user, 'split_thresholds', {})
    
    if not split_thresholds or all(threshold == 0 for threshold in split_thresholds.values()):
        await message.answer(
            localization.get_text(user.language, "need_splits_first") + "\n\n" +
            localization.get_text(user.language, "use_config"),
            parse_mode="HTML"
        )
        return
    
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

    await ensure_user_exists(user_id, message.from_user.username, message.from_user.first_name, state)
    user = user_manager.get_user(user_id)
    
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

    await ensure_user_exists(user_id, callback_query.from_user.username, callback_query.from_user.first_name, state)
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

    await ensure_user_exists(user_id, callback_query.from_user.username, callback_query.from_user.first_name, state)
    user = user_manager.get_user(user_id)
    data = callback_query.data
    
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
    
    if threshold == '0':
        threshold_text = localization.get_text(user.language, "dont_track")
    else:
        minutes = int(threshold) // 60
        seconds = int(threshold) % 60
        threshold_text = f"Sub {minutes}:{seconds:02d}"
    
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

@dp.callback_query(lambda c: c.data == 'splits')
async def splits_handler(callback_query: CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id

    await ensure_user_exists(user_id, callback_query.from_user.username, callback_query.from_user.first_name, state)
    user = user_manager.get_user(user_id)
    
    split_thresholds = getattr(user, 'split_thresholds', {})
    
    if not split_thresholds:
        await callback_query.message.edit_text(
            localization.get_text(user.language, "no_thresholds_set") + "\n\n" +
            localization.get_text(user.language, "configure_splits_first"),
            parse_mode="HTML",
            reply_markup=keyboards.get_splits_menu(user.language)
        )
        return
    
    message_text = localization.get_text(user.language, "current_thresholds") + "\n\n" + format_split_thresholds(split_thresholds, user.language)
    
    await callback_query.message.edit_text(
        message_text,
        parse_mode="HTML",
        reply_markup=keyboards.get_splits_menu(user.language)
    )


@dp.message(Command("get_users"))
async def get_users_file(message: Message):
    """Admin command to fetch the users file"""
    user_id = message.from_user.id
    user = user_manager.get_user(user_id)
    
    # Check if user is admin
    if not user or user.role != UserRole.ADMIN:
        await message.answer("❌ This command is for administrators only.")
        return
    
    config_file = user_manager.config_file
    
    try:
        # Check if file exists
        if not os.path.exists(config_file):
            await message.answer("❌ Users file not found.")
            return
        
        # Send the file
        file = FSInputFile(config_file, filename="users.json")
        await message.answer_document(
            document=file,
            caption="📊 Users database file"
        )
        
    except Exception as e:
        await message.answer(f"❌ Error fetching users file: {e}")

@dp.message(Command("config"))
async def config_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    await ensure_user_exists(user_id, message.from_user.username, message.from_user.first_name, state)
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
    
    await ensure_user_exists(user_id, callback_query.from_user.username, callback_query.from_user.first_name, state)
    user = user_manager.get_user(user_id)
    split_thresholds = getattr(user, 'split_thresholds', {})
    
    if not split_thresholds or all(threshold == 0 for threshold in split_thresholds.values()):
        await callback_query.answer(
            localization.get_text(user.language, "need_splits_first") + " " +
            localization.get_text(user.language, "configure_splits_first"),
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
    user_id = message.from_user.id
    await ensure_user_exists(user_id, message.from_user.username, message.from_user.first_name, state)
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
            localization.get_text(user.language, "please_use_commands") + "\n\n" + "/config",
            parse_mode="HTML"
        )

@dp.callback_query(lambda c: c.data == 'to_config')
async def back_to_config_handler(callback_query: CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    current_state = await state.get_state()
    user = user_manager.get_user(user_id)
    
    if current_state == UserStates.tracking_mode:
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

@dp.callback_query(lambda c: c.data in ['splits', 'OpenLanguageMenu', 'fortSplit', 'blindSplit', 'strongholdSplit', 'endSplit'])
async def config_menu_handler(callback_query: CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id

    await ensure_user_exists(user_id, callback_query.from_user.username, callback_query.from_user.first_name, state)
    user = user_manager.get_user(user_id)
    current_state = await state.get_state()
    
    if current_state == UserStates.tracking_mode:
        await callback_query.answer(
            localization.get_text(user.language, "configuration_disabled"),
            show_alert=True
        )
        return
    
    if callback_query.data == "splits":
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