import logging
import os
from io import BytesIO
import numpy as np
import pandas as pd
from aiogram import Router
from aiogram import types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    FSInputFile,
    ReplyKeyboardMarkup,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from scipy.stats import zscore
from FastRaschModel import FastRaschModel
from config import ADMIN_IDS
from db_rasch import TestManager  # Your database operations

router = Router()
logger = logging.getLogger(__name__)


def is_admin(user_id: int):
    return user_id in ADMIN_IDS


class TestStates(StatesGroup):
    waiting_for_test_data = State()
    waiting_for_test_id = State()
    waiting_for_test_id_rasch = State()


class AddTestStates(StatesGroup):
    waiting_for_input_type = State()
    # Single test path
    waiting_for_single_test_data = State()
    waiting_for_single_status = State()
    waiting_for_single_max_grade = State()
    # Excel path
    waiting_for_excel_file = State()
    waiting_for_excel_status = State()
    waiting_for_excel_max_grade = State()

class EditTestStates(StatesGroup):
    waiting_for_test_id = State()
    choosing_edit_option = State()
    editing_status = State()
    editing_answers = State()
    editing_max_grade = State()

class DeleteTestStates(StatesGroup):
    waiting_for_test_id = State()

class TestTakingStates(StatesGroup):
    waiting_for_test_id = State()
    waiting_for_first_name_data = State()
    waiting_for_second_name_data = State()
    waiting_for_third_name_data = State()
    waiting_for_region_data = State()
    answering_questions = State()
    answering_part_a = State()
    answering_part_b = State()
    ready_to_submit = State()


# ADMIN keyboard
def get_admin_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="➕ Test qo'shish")
    builder.button(text="🗑 Test o'chirish")
    builder.button(text="📜 Barcha testlar")
    builder.button(text="Rasch Result")
    builder.button(text="Edit")
    builder.button(text="Export Results")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)


# USER keyboard
def get_user_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="📝 Test ishlash")
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)


@router.message(Command("start"))
async def start_command(message: types.Message):
    try:
        user_id = message.from_user.id
        channel_username = '@matematikadanonlinetestlar'  # masalan: '@mychannel'

        try:
            member = await message.bot.get_chat_member(channel_username, user_id)
            if member.status not in ("member", "administrator", "creator"):
                invite_link = f"https://t.me/{channel_username.lstrip('@')}"
                await message.answer(
                    f"Botdan foydalanishdan oldin quyidagi kanalga a'zo bo'lishingiz kerak:\n\n👉 {invite_link}\n\nA'zo bo‘lgach, /start buyrug'ini qayta yuboring."
                )
                return
        except Exception as e:
            await message.answer("A'zolikni tekshirib bo‘lmadi. Iltimos, keyinroq urinib ko‘ring.")
            return

        photo_path = "images/welcometc.PNG"
        if not os.path.exists(photo_path):
            raise FileNotFoundError(f"Rasm topilmadi: {photo_path}")

        photo = FSInputFile(photo_path)
        if is_admin(message.from_user.id):
            caption = "Assalomu alaykum, Admin!\n\nQuyidagi tugmalarda foydalaning:"
            reply_markup = get_admin_keyboard()
        else:
            caption = "Assalomu alaykum!\n\nTest javoblarini yuborish uchun quyidagi '📝 Test ishlash' tugmasini bosing:\n\n❗️❗️❗️ Eslatib o'tamiz bot hozir test rejimida ishlayapti. Xato va kamchiliklar uchun oldindan uzr so'raymiz.❗️❗️❗"
            reply_markup = get_user_keyboard()

        await message.answer_photo(photo=photo, caption=caption, reply_markup=reply_markup)

    except FileNotFoundError as e:
        logger.warning(str(e))
        await message.answer(
            "Xush kelibsiz!\n\nQuyidagi tugmalardan foydalaning:",
            reply_markup=get_admin_keyboard() if is_admin(message.from_user.id) else get_user_keyboard()
        )
    except Exception as e:
        logger.error(f"Start commandda xato: {e}", exc_info=True)
        await message.answer(
            "Xush kelibsiz! Botda xatolik yuz berdi.",
            reply_markup=get_admin_keyboard() if is_admin(message.from_user.id) else get_user_keyboard()
        )


# Input type keyboard
def get_input_type_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Single", callback_data="input_type:single"),
        InlineKeyboardButton(text="Excel file", callback_data="input_type:excel")
    )
    builder.row(InlineKeyboardButton(text="Back", callback_data="input_type:back"))
    return builder.as_markup()


# Status keyboard
def get_status_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Active", callback_data="status:active"),
        InlineKeyboardButton(text="Inactive", callback_data="status:inactive")
    )
    builder.row(InlineKeyboardButton(text="Back", callback_data="status:back"))
    return builder.as_markup()


# Max grade keyboard
def get_max_grade_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="93", callback_data="max_grade:93"),
        InlineKeyboardButton(text="63", callback_data="max_grade:63"),
        InlineKeyboardButton(text="75", callback_data="max_grade:75")
    )
    builder.row(InlineKeyboardButton(text="Back", callback_data="max_grade:back"))
    return builder.as_markup()


# Start test addition
@router.message(F.text == "➕ Test qo'shish")
async def add_test_command(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return await message.answer("Siz admin emassiz!")

    await state.set_state(AddTestStates.waiting_for_input_type)
    await message.answer(
        "Test qo'shish usulini tanlang:",
        reply_markup=get_input_type_keyboard()
    )


@router.callback_query(AddTestStates.waiting_for_input_type, F.data.startswith("input_type:"))
async def process_input_type(callback: types.CallbackQuery, state: FSMContext):
    input_type = callback.data.split(":")[1]

    if input_type == "back":
        await state.clear()
        return await callback.message.edit_text("Bekor qilindi.")

    if input_type == "single":
        await state.set_state(AddTestStates.waiting_for_single_test_data)
        await callback.message.answer(
            "Test ma'lumotlarini quyidagi formatda yuboring:\n\n"
            "<code>test_id:javoblar</code>",
            reply_markup=types.ReplyKeyboardRemove()
        )
        await callback.message.delete()
    elif input_type == "excel":
        await state.set_state(AddTestStates.waiting_for_excel_file)
        await callback.message.answer(
            "Excel faylini yuboring (.xlsx formatida).\n"
            "Fayl strukturasi:\n"
            "1-ustun: test_id\n"
            "2-ustun: 1-35 savollar javoblari (35 ta A-F)",
            reply_markup=types.ReplyKeyboardRemove()
        )
        await callback.message.delete()


@router.message(AddTestStates.waiting_for_single_test_data, F.text)
async def receive_single_test(message: Message, state: FSMContext):
    try:
        if ":" not in message.text:
            raise ValueError("Format not valid")

        test_id, answers = message.text.split(":", 1)
        test_id = test_id.strip().lower()
        answers = answers.strip()

        parts = answers.split()

        # Validate answers format
        parts = answers.split(';')
        if len(parts) != 21:  # 35 letters + 20 math answers
            raise ValueError("Noto'g'ri javoblar formati. 35 ta harf va 20 ta matematik javob bo'lishi kerak")



        # Validate Q1-35 answers
        if len(parts[0]) != 35:
            raise ValueError("1-35 savollar uchun 35 ta javob bo'lishi kerak")
        if not all(c in 'ABCDEF' for c in parts[0].upper()):
            raise ValueError("1-35 savollar faqat A,B,C,D,E,F harflaridan iborat bo'lishi kerak")

        full_answers = answers + ";" + ";".join([""] * 20)

        await state.update_data(test_id=test_id, answers=full_answers)
        await state.set_state(AddTestStates.waiting_for_single_status)
        await message.answer(
            "✅ Test ma'lumotlari qabul qilindi!\n"
            "Endi statusni tanlang:",
            reply_markup=get_status_keyboard()
        )

    except ValueError as e:
        builder = InlineKeyboardBuilder()
        builder.add(InlineKeyboardButton(text="🔙 Orqaga", callback_data="input_error_back"))
        await message.answer(
            f"❌ Xato: {e}\n\n"
            "Iltimos, quyidagi formatda yuboring:\n\n"
            "<code>test_id:javoblar</code>",
            reply_markup=builder.as_markup()
        )


@router.message(AddTestStates.waiting_for_excel_file, F.document)
async def receive_excel_file(message: Message, state: FSMContext):
    if not message.document.file_name.endswith(('.xlsx', '.xls')):
        builder = InlineKeyboardBuilder()
        builder.add(InlineKeyboardButton(text="🔙 Orqaga", callback_data="input_error_back"))
        return await message.answer(
            "Iltimos, .xlsx yoki .xls formatidagi fayl yuboring!",
            reply_markup=builder.as_markup()
        )

    try:
        file = await message.bot.get_file(message.document.file_id)
        file_bytes = await message.bot.download_file(file.file_path)

        df = pd.read_excel(BytesIO(file_bytes.read()))
        if len(df.columns) < 22:
            raise ValueError("Excelda kamida 22 ustun bo'lishi kerak (test_id, 35 harf, 20 matematik javob)")

        tests = []
        for _, row in df.iterrows():
            test_id = str(row[0]).lower()
            answers_1_35 = str(row[1]).upper()

            # Validate Q1-35
            if len(answers_1_35) != 35:
                raise ValueError(f"{test_id}: 1-35 savollar uchun 35 ta javob bo'lishi kerak")
            if not all(c in 'ABCDEF' for c in answers_1_35):
                raise ValueError(f"{test_id}: 1-35 savollar faqat A-F harflaridan iborat bo'lishi kerak")

            # Prepare math answers
            math_answers = []
            for i in range(2, 22):
                math_answers.append(str(row[i]).strip())

            tests.append({
                'test_id': test_id,
                'answers': answers_1_35 + ";" + ";".join(math_answers)
            })

        await state.update_data(excel_tests=tests)
        await state.set_state(AddTestStates.waiting_for_excel_status)
        await message.answer(
            f"✅ {len(tests)} ta test yuklandi!\nStatusni tanlang:",
            reply_markup=get_status_keyboard()
        )

    except Exception as e:
        builder = InlineKeyboardBuilder()
        builder.add(InlineKeyboardButton(text="🔙 Orqaga", callback_data="input_error_back"))
        await message.answer(
            f"❌ Xatolik: {str(e)}",
            reply_markup=builder.as_markup()
        )
        logger.error(f"Excel processing error: {e}")


@router.callback_query(F.data == "input_error_back")
async def handle_input_error_back(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddTestStates.waiting_for_input_type)
    await callback.message.edit_text(
        "Test qo'shish usulini tanlang:",
        reply_markup=get_input_type_keyboard()
    )
    await callback.answer()

# Add these handlers before your process_status function
@router.callback_query(
    AddTestStates.waiting_for_single_status,
    F.data.startswith("status:")
)
async def handle_single_status(callback: CallbackQuery, state: FSMContext):
    await process_status(callback, state, "single")

@router.callback_query(
    AddTestStates.waiting_for_excel_status,
    F.data.startswith("status:")
)
async def handle_excel_status(callback: CallbackQuery, state: FSMContext):
    await process_status(callback, state, "excel")

async def process_status(callback: CallbackQuery, state: FSMContext, path_type: str):
    try:
        # Verify we're in the correct state
        current_state = await state.get_state()
        expected_states = [
            AddTestStates.waiting_for_single_status,
            AddTestStates.waiting_for_excel_status
        ]

        if current_state not in expected_states:
            await callback.answer("Invalid state for this action")
            return

        # Extract status
        status = callback.data.split(":")[1]

        # Handle back button
        if status == "back":
            await callback.answer()
            prev_state = (
                AddTestStates.waiting_for_single_test_data
                if path_type == "single"
                else AddTestStates.waiting_for_excel_file
            )
            await state.set_state(prev_state)

            # Different messages for different paths
            text = (
                "Test ma'lumotlarini quyidagi formatda yuboring:\n"
                "<code>test_id:javoblar</code>"
                if path_type == "single"
                else "Excel faylini yuboring (.xlsx formatida)"
            )

            try:
                await callback.message.edit_text(text, reply_markup=None)
            except:
                await callback.message.answer(text)
            return

        # Handle status selection
        await state.update_data(status=status)
        await callback.answer(f"Status set to {status}")

        # Move to max grade selection
        next_state = (
            AddTestStates.waiting_for_single_max_grade
            if path_type == "single"
            else AddTestStates.waiting_for_excel_max_grade
        )
        await state.set_state(next_state)

        try:
            await callback.message.edit_text(
                "Maksimal bahoni tanlang:",
                reply_markup=get_max_grade_keyboard()
            )
        except:
            await callback.message.answer(
                "Maksimal bahoni tanlang:",
                reply_markup=get_max_grade_keyboard()
            )

    except Exception as e:
        logger.error(f"Status processing error: {e}")
        await callback.answer("Xatolik yuz berdi, qayta urinib ko'ring")


# Max grade handlers
@router.callback_query(
    AddTestStates.waiting_for_single_max_grade,
    F.data.startswith("max_grade:")
)
async def handle_single_max_grade(callback: CallbackQuery, state: FSMContext):
    await process_max_grade(callback, state, "single")

@router.callback_query(
    AddTestStates.waiting_for_excel_max_grade,
    F.data.startswith("max_grade:")
)
async def handle_excel_max_grade(callback: CallbackQuery, state: FSMContext):
    await process_max_grade(callback, state, "excel")

async def process_max_grade(callback: CallbackQuery, state: FSMContext, path_type: str):
    max_grade = callback.data.split(":")[1]
    data = await state.get_data()

    try:
        if path_type == "single":
            await TestManager.save_single_test(
                test_id=data['test_id'],
                answers=data['answers'],
                status=data['status'],
                max_grade=int(max_grade)
            )
            await callback.message.edit_text(
                f"✅ Test qo'shildi!\n\n"
                f"Test ID: {data['test_id']}\n"
                f"Status: {data['status']}\n"
                f"Max grade: {max_grade}"
            )
        else:
            tests = [{
                'test_id': t['test_id'],
                'answers': t['answers'],
                'status': data['status'],
                'max_grade': int(max_grade)
            } for t in data['excel_tests']]

            await TestManager.bulk_insert_tests(tests)
            await callback.message.edit_text(
                f"✅ {len(tests)} ta test qo'shildi!\n\n"
                f"Status: {data['status']}\n"
                f"Max grade: {max_grade}"
            )

        await callback.message.answer(
            "Bosh menyu:",
            reply_markup=get_admin_keyboard()
        )

    except Exception as e:
        logger.error(f"Test save error: {e}")
        await callback.message.answer(
            f"❌ Test saqlashda xatolik: {str(e)}",
            reply_markup=get_admin_keyboard()
        )
    finally:
        await state.clear()

@router.message(F.text == "🗑 Test o'chirish")
async def delete_test_command(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return await message.answer("Siz admin emassiz!")

    await state.set_state(DeleteTestStates.waiting_for_test_id)
    await message.answer(
        "O'chirish uchun test ID sini yuboring:",
        reply_markup=types.ReplyKeyboardRemove()  # This removes reply keyboard
    )


@router.message(DeleteTestStates.waiting_for_test_id, F.text)
async def process_test_id_for_deletion(message: types.Message, state: FSMContext):
    test_id = message.text.strip().lower()

    # First check if test exists
    test_exists = await TestManager.get_test(test_id)
    if not test_exists:
        await message.answer(
            f"❌ Test ID {test_id} topilmadi!",
            reply_markup=get_admin_keyboard()
        )
        await state.clear()
        return

    # If exists, store ID and ask for confirmation
    await state.update_data(test_id=test_id)

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Ha", callback_data="confirm_delete"),
        InlineKeyboardButton(text="❌ Yo'q", callback_data="cancel_delete")
    )

    await message.answer(
        f"Test ID {test_id} topildi. Rostdan ham o'chirmoqchimisiz?",
        reply_markup=builder.as_markup()
    )


@router.callback_query(F.data == "confirm_delete")
async def confirm_deletion(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    test_id = data['test_id']

    try:
        success = await TestManager.delete_test(test_id)
        if success:
            await callback.message.edit_text(
                f"✅ Test ID {test_id} muvaffaqiyatli o'chirildi!",
                reply_markup=None
            )
        else:
            await callback.message.edit_text(
                f"❌ Test ID {test_id} o'chirishda xatolik!",
                reply_markup=None
            )

        # Send admin keyboard in a new message
        await callback.message.answer(
            "Bosh menyu:",
            reply_markup=get_admin_keyboard()
        )

    except Exception as e:
        logger.error(f"Error deleting test {test_id}: {e}")
        await callback.message.edit_text(
            f"❌ Xatolik yuz berdi: {str(e)}",
            reply_markup=None
        )
        await callback.message.answer(
            "Bosh menyu:",
            reply_markup=get_admin_keyboard()
        )

    await callback.answer()
    await state.clear()


@router.callback_query(F.data == "cancel_delete")
async def cancel_deletion(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    test_id = data['test_id']

    await callback.message.edit_text(
        f"Test ID {test_id} o'chirish bekor qilindi.",
        reply_markup=None
    )
    await callback.message.answer(
        "Bosh menyu:",
        reply_markup=get_admin_keyboard()
    )
    await callback.answer()
    await state.clear()

@router.message(F.text == "Edit")
async def edit_test_command(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return await message.answer("Siz admin emassiz!")

    await state.set_state(EditTestStates.waiting_for_test_id)
    await message.answer(
        "Tahrirlash uchun test ID sini yuboring:",
        reply_markup=types.ReplyKeyboardRemove()
    )


@router.message(EditTestStates.waiting_for_test_id, F.text)
async def process_test_id_for_edit(message: types.Message, state: FSMContext):
    test_id = message.text.strip().lower()

    test = await TestManager.get_test(test_id)
    if not test:
        await message.answer(
            f"❌ Test ID {test_id} topilmadi!",
            reply_markup=get_admin_keyboard()
        )
        await state.clear()
        return

    await state.update_data(test_id=test_id, current_test=test)

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Status", callback_data="edit_status"),
        InlineKeyboardButton(text="Javoblar", callback_data="edit_answers")
    )
    builder.row(
        InlineKeyboardButton(text="Max grade", callback_data="edit_max_grade"),
        InlineKeyboardButton(text="Bekor qilish", callback_data="cancel_edit")
    )

    await message.answer(
        f"Test ID {test_id} uchun nima tahrirlamoqchisiz?",
        reply_markup=builder.as_markup()
    )
    await state.set_state(EditTestStates.choosing_edit_option)


# Status editing
@router.callback_query(EditTestStates.choosing_edit_option, F.data == "edit_status")
async def edit_status_handler(callback: CallbackQuery, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Active", callback_data="set_status:active"),
        InlineKeyboardButton(text="Inactive", callback_data="set_status:inactive")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Orqaga", callback_data="back_to_edit_options")
    )

    await callback.message.edit_text(
        "Yangi statusni tanlang:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(EditTestStates.editing_status)
    await callback.answer()


@router.callback_query(EditTestStates.editing_status, F.data.startswith("set_status:"))
async def set_status_handler(callback: CallbackQuery, state: FSMContext):
    new_status = callback.data.split(":")[1]
    data = await state.get_data()

    try:
        await TestManager.update_test(
            test_id=data['test_id'],
            status=new_status
        )
        await callback.message.edit_text(
            f"✅ Test ID {data['test_id']} statusi {new_status} ga o'zgartirildi!"
        )
    except Exception as e:
        logger.error(f"Error updating status: {e}")
        await callback.message.edit_text(
            f"❌ Statusni o'zgartirishda xatolik: {e}"
        )

    await show_edit_options_after_update(callback, state)


# Answers editing
@router.callback_query(EditTestStates.choosing_edit_option, F.data == "edit_answers")
async def edit_answers_handler(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Yangi javoblarni yuboring:",
        reply_markup=InlineKeyboardBuilder()
        .add(InlineKeyboardButton(text="◀️ Orqaga", callback_data="back_to_edit_options"))
        .as_markup()
    )
    await state.set_state(EditTestStates.editing_answers)
    await callback.answer()


@router.message(EditTestStates.editing_answers, F.text)
async def set_answers_handler(message: types.Message, state: FSMContext):
    new_answers = message.text.strip().lower()
    data = await state.get_data()

    try:
        await TestManager.update_test(
            test_id=data['test_id'],
            answers=new_answers
        )
        await message.answer(
            f"✅ Test ID {data['test_id']} javoblari yangilandi!"
        )
    except Exception as e:
        logger.error(f"Error updating answers: {e}")
        await message.answer(
            f"❌ Javoblarni yangilashda xatolik: {e}"
        )

    await show_edit_options_after_update(message, state)

# Max grade editing
@router.callback_query(EditTestStates.choosing_edit_option, F.data == "edit_max_grade")
async def edit_max_grade_handler(callback: CallbackQuery, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="93", callback_data="set_grade:93"),
        InlineKeyboardButton(text="63", callback_data="set_grade:63"),
        InlineKeyboardButton(text="75", callback_data="set_grade:75")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Orqaga", callback_data="back_to_edit_options")
    )

    await callback.message.edit_text(
        "Yangi max grade ni tanlang:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(EditTestStates.editing_max_grade)
    await callback.answer()


@router.callback_query(EditTestStates.editing_max_grade, F.data.startswith("set_grade:"))
async def set_max_grade_handler(callback: CallbackQuery, state: FSMContext):
    try:
        new_grade = int(callback.data.split(":")[1])  # Convert to integer
        data = await state.get_data()

        await TestManager.update_test(
            test_id=data['test_id'],
            max_grade=new_grade
        )
        await callback.message.edit_text(
            f"✅ Test ID {data['test_id']} max grade {new_grade} ga o'zgartirildi!"
        )
    except ValueError:
        await callback.message.edit_text(
            "❌ Noto'g'ri max grade formati! Iltimos, raqam kiriting."
        )
    except Exception as e:
        logger.error(f"Error updating max grade: {e}")
        await callback.message.edit_text(
            f"❌ Max grade ni o'zgartirishda xatolik: {e}"
        )

    await show_edit_options_after_update(callback, state)


# Common handlers
@router.callback_query(F.data == "cancel_edit", EditTestStates.choosing_edit_option)
async def cancel_edit_handler(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Tahrirlash bekor qilindi."
    )
    await callback.message.answer(
        "Bosh menyu:",
        reply_markup=get_admin_keyboard()
    )
    await state.clear()
    await callback.answer()


@router.callback_query(F.data == "finish_editing", EditTestStates.choosing_edit_option)
async def finish_editing_handler(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await callback.message.edit_text(
        f"Test ID {data['test_id']} tahrirlash tugatildi."
    )
    await callback.message.answer(
        "Bosh menyu:",
        reply_markup=get_admin_keyboard()
    )
    await state.clear()
    await callback.answer()


async def show_edit_options_after_update(update: types.Message | types.CallbackQuery, state: FSMContext):
    data = await state.get_data()

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Status", callback_data="edit_status"),
        InlineKeyboardButton(text="Javoblar", callback_data="edit_answers")
    )
    builder.row(
        InlineKeyboardButton(text="Max grade", callback_data="edit_max_grade"),
        InlineKeyboardButton(text="Tugatish", callback_data="finish_editing")
    )

    if isinstance(update, types.CallbackQuery):
        await update.message.answer(
            f"Test ID {data['test_id']} uchun yana nima tahrirlamoqchisiz?",
            reply_markup=builder.as_markup()
        )
    else:
        await update.answer(
            f"Test ID {data['test_id']} uchun yana nima tahrirlamoqchisiz?",
            reply_markup=builder.as_markup()
        )

    await state.set_state(EditTestStates.choosing_edit_option)


@router.message(F.text == "📜 Barcha testlar")
async def list_all_tests(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("Siz admin emassiz!")

    try:
        # Get all tests from database
        tests = await TestManager.get_all_tests()

        if not tests:
            return await message.answer("Hozircha testlar mavjud emas!")

        # Format the tests into a readable message
        response = ["📊 Barcha testlar ro'yxati:\n"]
        for test in tests:
            created_date = test['created_at'].strftime("%Y-%m-%d %H:%M")
            response.append(
                f"\n🔹 Test ID: {test['test_id']}\n"
                f"Javoblar: {test['answers']}\n"
                f"Status: {test['status']}\n"
                f"Max grade: {test['max_grade']}\n"
                f"Qo'shilgan sana: {created_date}\n"
                f"{'-' * 30}"
            )

        # Split long messages to avoid Telegram limits
        chunk_size = 10  # Number of tests per message
        for i in range(0, len(response), chunk_size):
            chunk = response[i:i + chunk_size]
            await message.answer('\n'.join(chunk))

    except Exception as e:
        logger.error(f"Error listing tests: {e}")
        await message.answer("Testlarni olishda xatolik yuz berdi!")


@router.message(F.text == "Export Results")
async def request_test_id(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Sizda bunday huquq yo'q!")
        return

    await state.set_state(TestStates.waiting_for_test_id)
    await message.answer(
        "📝 Eksport qilish uchun test ID sini yuboring:",
        reply_markup=types.ReplyKeyboardRemove()
    )


@router.message(TestStates.waiting_for_test_id, F.text)
async def process_export(message: Message, state: FSMContext):
    test_id = message.text.strip().lower()

    try:
        # Show loading message
        processing_msg = await message.answer("⏳ Natijalar tayyorlanmoqda...")

        excel_file = await TestManager.export_test_results(test_id)

        # Delete loading message
        await processing_msg.delete()

        await message.answer_document(
            document=excel_file,
            caption=f"Test {test_id} natijalari",
            reply_markup=get_admin_keyboard()
        )
    except ValueError as e:
        await message.answer(f"❌ {str(e)}\n\nIltimos, to'g'ri test ID sini kiriting:")
    except Exception as e:
        logger.error(f"Export error: {str(e)}")
        await message.answer("❌ Natijalarni eksport qilishda xatolik yuz berdi!")
    finally:
        await state.clear()

@router.message(F.text == "Rasch Result")
async def request_rasch_test_id(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Sizda bunday huquq yo'q!")
        return

    await state.set_state(TestStates.waiting_for_test_id_rasch)
    await message.answer(
        "📝 Rasch natijalarini olish uchun test ID sini yuboring:",
        reply_markup=types.ReplyKeyboardRemove()
    )


@router.message(TestStates.waiting_for_test_id_rasch, F.text)
async def process_rasch_model(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Siz admin emassiz!\n Shuning uchun bizning botdan foydalana olmaysiz!")

    test_id = message.text.strip().lower()

    processing_msg_rasch = await message.answer("Test natijalari analiz qilinyapti...")


    try:
        print("Loading data...")

        df = await TestManager.export_df_results(test_id)

        print(f"Data loaded successfully with {len(df)} rows")
        print("Faylda mavjud ustunlar:", df.columns.tolist())

        # Agar ustun nomlari boshqacha bo'lsa, ularni moslashtiring
        required_columns = ['№', 'F.I.O.', 'Duris']
        available_columns = df.columns.tolist()

        # Ustun nomlarini tekshirish va moslashtirish
        if not all(col in available_columns for col in required_columns):
            # Agar standart nomlar topilmasa, birinchi 3 ustundan foydalaning
            if len(df.columns) >= 3:
                df.columns = ['№', 'F.I.O.', 'Duris'] + list(df.columns[3:])
                print("Ustun nomlari avtomatik moslashtirildi")
            else:
                raise ValueError("Faylda kamida 3 ta ustun bo'lishi kerak")

        # Column handling
        if len(df.columns) < 3:
            raise ValueError("File must have at least 3 columns")

        # Auto-detect response columns (assuming they start from column 3)
        response_cols = df.columns[3:]
        print(f"Detected {len(response_cols)} response columns")

        # Convert responses to binary (1 for correct, 0 for incorrect)
        response_data = df[response_cols].applymap(lambda x: 1 if x == 1 else 0)

        # Fit Rasch model with progress tracking
        print("Fitting Rasch model...")
        model = FastRaschModel()
        model.fit(response_data)

        # Calculate scores
        print("Calculating scores...")
        df['Theta'] = model.person_ability
        df['Ball'] = 50 + 10 * zscore(df['Theta'])
        df['Ball'] = np.round(df['Ball'], 2)

        df['Ball'] = df['Ball'] + np.random.uniform(-0.05, 0.05, size=len(df['Ball']))
        df['Ball'] = df['Ball'].round(decimals=2)

        # Determine subject type based on max possible score
        max_possible = len(response_cols)
        subject_type = "1-fan" if max_possible >= 45 else "2-fan"

        # Calculate proportional scores
        theta_min = df['Theta'].min()
        theta_range = df['Theta'].max() - theta_min
        if theta_range > 0:
            df['Prop_Score'] = ((df['Theta'] - theta_min) / theta_range) * (max_possible - 65) + 65
        else:
            df['Prop_Score'] = 65  # Handle case where all abilities are equal

        # Assign grades
        bins = [0, 46, 50, 55, 60, 65, 70, 93]
        labels = ['NC', 'C', 'C+', 'B', 'B+', 'A', 'A+']
        df['Daraja'] = pd.cut(df['Ball'], bins=bins, labels=labels, right=False)

        # Save results
        result_cols = ['№', 'F.I.O.', 'Ball', 'Daraja']
        if '№' not in df.columns:
            result_cols = [col for col in result_cols if col != '№']

        print("Saving results...")
        result_path = f'rasch_{test_id}_natijalar.xlsx'

        df = df.sort_values(by='Ball', ascending=False)
        df['№'] = range(1, len(df) + 1)
        df[result_cols].to_excel(result_path, index=False, engine='openpyxl')

        await processing_msg_rasch.delete()

        result_file = types.FSInputFile(result_path)
        await message.answer_document(
            document=result_file,
            caption=f'Rasch analiz tugadi!',
            reply_markup=get_admin_keyboard()
        )

    except ValueError as e:
        if "At least one sheet must be visible" in str(e):
            await message.answer(
                "Error: The Excel file has no visible sheets. Please ensure at least one sheet is visible and contains data."
            )
        else:
            print(f"Error: {str(e)}")
            await message.answer(f"Error processing file: {str(e)}")
    except Exception as e:
        print(f"Error processing file: {str(e)}")
        await message.answer(f"Error processing file: {str(e)}")
    finally:
        if 'result_path' in locals() and os.path.exists(result_path):
            os.remove(result_path)




#####---------------------------USER--------------------------------------------
#start handler
@router.message(F.text == "📝 Test ishlash")
async def start_test(message: Message, state: FSMContext):
    telegram_id = message.from_user.id
    url = f"https://exam-elf.web.app?telegram_id={telegram_id}"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Testni boshlash", url=url)]
        ]
    )

    await message.answer("Testni shu yerda boshlang:", reply_markup=keyboard)



@router.message()
async def handle_unknown_messages(message: types.Message, state: FSMContext):
    current_state = await state.get_state()

    # If in specific state, give state-specific guidance
    if current_state == AddTestStates.waiting_for_single_test_data:
        await message.answer(
            "❌ Noto'g'ri format!\n\n"
            "Iltimos, quyidagi formatda yuboring:\n"
            "<code>test_id:javoblar</code>\n\n"
            "Misol: <code>12345:abcdeabcdabcdeabcdabcde</code>",
            reply_markup=InlineKeyboardBuilder()
            .add(InlineKeyboardButton(text="🔙 Orqaga", callback_data="input_error_back"))
            .as_markup()
        )
    elif current_state == AddTestStates.waiting_for_excel_file:
        await message.answer(
            "❌ Noto'g'ri fayl formati!\n\n"
            "Iltimos, .xlsx yoki .xls formatidagi fayl yuboring.",
            reply_markup=InlineKeyboardBuilder()
            .add(InlineKeyboardButton(text="🔙 Orqaga", callback_data="input_error_back"))
            .as_markup()
        )
    # Default message for all other cases
    else:
        if is_admin(message.from_user.id):
            await message.answer(
                "❌ Noto'g'ri buyruq!\n\n"
                "Iltimos, quyidagilardan birini tanlang:",
                reply_markup=get_admin_keyboard()
            )
        else:
            await message.answer(
                "❌ Noto'g'ri buyruq!\n\n"
                "Test ishlash uchun quyidagi tugmani bosing:",
                reply_markup=get_user_keyboard()
            )






#
# #process test id
# @router.message(TestTakingStates.waiting_for_test_id, F.text)
# async def process_test_id(message: Message, state: FSMContext):
#     test_id = message.text.strip()
#
#     # Get test data from database
#     test = await TestManager.get_test(test_id)
#     if not test:
#         await message.answer(
#             "❌ Bu test bazada topilmadi!",
#             reply_markup=get_user_keyboard()
#         )
#         await state.clear()
#         return
#
#     # Store test ID and initialize test data
#     await state.update_data(
#         test_id=test_id,
#         user_answers=[''] * 35,
#         current_question=0
#     )
#
#     # Start collecting user data
#     await state.set_state(TestTakingStates.waiting_for_first_name_data)
#     await message.answer(
#         "Ismingizni kiriting:",
#         reply_markup=types.ReplyKeyboardRemove()
#     )
#
#
# # Collect first name
# @router.message(TestTakingStates.waiting_for_first_name_data, F.text)
# async def process_first_name(message: Message, state: FSMContext):
#     first_name = message.text.strip()
#     await state.update_data(first_name=first_name)
#     await state.set_state(TestTakingStates.waiting_for_second_name_data)
#     await message.answer(
#         "Familyangizni kiriting:",
#         reply_markup=types.ReplyKeyboardRemove()
#     )
#
#
# # Collect second name
# @router.message(TestTakingStates.waiting_for_second_name_data, F.text)
# async def process_second_name(message: Message, state: FSMContext):
#     second_name = message.text.strip()
#     await state.update_data(second_name=second_name)
#     await state.set_state(TestTakingStates.waiting_for_third_name_data)
#     await message.answer(
#         "Otangizning ismini kiriting:\n\nMisol: Anvar o'g'li (qizi):",
#         reply_markup=types.ReplyKeyboardRemove()
#     )
#
#
# # Collect third name (patronymic)
# @router.message(TestTakingStates.waiting_for_third_name_data, F.text)
# async def process_third_name(message: Message, state: FSMContext):
#     third_name = message.text.strip()
#     await state.update_data(third_name=third_name)
#     await state.set_state(TestTakingStates.waiting_for_region_data)
#     await message.answer(
#         "Viloyat yoki tumaningizni kiriting:",
#         reply_markup=types.ReplyKeyboardRemove()
#     )
#
#
# # Collect region and start the test
# @router.message(TestTakingStates.waiting_for_region_data, F.text)
# async def process_region(message: Message, state: FSMContext):
#     region = message.text.strip()
#     await state.update_data(region=region)
#
#     # All user data collected, now start the test
#     await ask_question(message, state)
#
#
#
# # Display current question
# async def ask_question(update: Union[Message, CallbackQuery], state: FSMContext):
#     await state.set_state(TestTakingStates.answering_questions)
#
#     data = await state.get_data()
#     question_num = data.get("current_question", 0)
#     # Create appropriate keyboard based on question type
#     if question_num < 32:  # Questions 1-32 (A-D)
#         keyboard = [
#             [InlineKeyboardButton(text="A", callback_data="answer:A"),
#              InlineKeyboardButton(text="B", callback_data="answer:B")],
#              [InlineKeyboardButton(text="C", callback_data="answer:C"),
#              InlineKeyboardButton(text="D", callback_data="answer:D")]
#         ]
#     elif question_num < 35:  # Questions 33-35 (A-F)
#         keyboard = [
#             [InlineKeyboardButton(text="A", callback_data="answer:A"),
#              InlineKeyboardButton(text="B", callback_data="answer:B"),
#              InlineKeyboardButton(text="C", callback_data="answer:C")],
#             [InlineKeyboardButton(text="D", callback_data="answer:D"),
#              InlineKeyboardButton(text="E", callback_data="answer:E"),
#              InlineKeyboardButton(text="F", callback_data="answer:F")]
#         ]
#
#     # # Add navigation buttons
#     nav_buttons = []
#     if question_num > 0:
#         nav_buttons.append(InlineKeyboardButton(text="◀️ Orqaga", callback_data="prev_question"))
#     if question_num < 34:          #--------------------------------------
#         nav_buttons.append(InlineKeyboardButton(text="➡️ O'tkazish", callback_data="skip_question"))
#     if nav_buttons:
#         keyboard.append(nav_buttons)
#
#     text = f"Savol {question_num + 1}/35: Marhamat quyidagilardan birini tanlang!\n"
#
#     reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
#
#     if isinstance(update, CallbackQuery):
#         await update.message.edit_text(text, reply_markup=reply_markup)
#     elif isinstance(update, Message):
#         await update.answer(text, reply_markup=reply_markup)
#
#
# # Handle single answer (A-F)
# @router.callback_query(
#     TestTakingStates.answering_questions,
#     F.data.startswith("answer:")
# )
# async def handle_single_answer(callback: CallbackQuery, state: FSMContext):
#     try:
#         answer = callback.data.split(":")[1]
#         data = await state.get_data()
#         question_num = data['current_question']
#
#         user_answers = data['user_answers']
#         user_answers[question_num] = answer
#         await state.update_data(user_answers=user_answers)
#
#         await next_question(callback, state)
#         await callback.answer()
#     except Exception as e:
#         await callback.message.answer(f"Xatolik yuz berdi: {str(e)}")
#         await callback.answer()
#
#
# # Previous question
# @router.callback_query(F.data == "prev_question")
# async def prev_question(callback: CallbackQuery, state: FSMContext):
#     data = await state.get_data()
#     question_num = data['current_question']
#
#     if question_num > 0:
#         await state.update_data(current_question=question_num - 1)
#         await state.set_state(TestTakingStates.answering_questions)
#         await ask_question(callback, state)
#
#     await callback.answer()
#
#
# # Skip question
# @router.callback_query(F.data == "skip_question")
# async def skip_question(callback: CallbackQuery, state: FSMContext):
#     data = await state.get_data()
#     question_num = data['current_question']
#
#     if question_num < 34:
#         await state.update_data(current_question=question_num + 1)
#         await state.set_state(TestTakingStates.answering_questions)
#         await ask_question(callback, state)
#
#     await callback.answer()
#
#
# # Move to next question
# async def next_question(update: Union[Message, CallbackQuery], state: FSMContext):
#     data = await state.get_data()
#     question_num = data['current_question'] + 1
#
#     if question_num >= 35:
#         await state.set_state(TestTakingStates.ready_to_submit)
#
#         keyboard = [
#             [InlineKeyboardButton(text="✅ Javoblarni tekshirish", callback_data="submit_answers")],
#             [InlineKeyboardButton(text="🔄 Qayta ishlash", callback_data="restart_test")]
#         ]
#         reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
#
#         text = "Barcha javoblarni kiritdingiz!\nInternetga ulanganda «Javoblarni tekshirish» tugmasini bosing."
#
#         if isinstance(update, CallbackQuery):
#             await update.message.edit_text(text, reply_markup=reply_markup)
#         else:
#             await update.answer(text, reply_markup=reply_markup)
#         return
#
#     await state.update_data(current_question=question_num)
#     await state.set_state(TestTakingStates.answering_questions)
#     await ask_question(update, state)
#
#
#
# #submit_answers
# @router.callback_query(TestTakingStates.ready_to_submit, F.data == "submit_answers")
# async def submit_answers(callback: CallbackQuery, state: FSMContext):
#     data = await state.get_data()
#     test_id = data['test_id'].strip()
#     user_id = callback.from_user.id
#     user_data = {
#         'first_name': data.get('first_name', ''),
#         'second_name': data.get('second_name', ''),
#         'third_name': data.get('third_name', ''),
#         'region': data.get('region', '')
#     }
#     user_answers = data['user_answers']
#
#     try:
#         # Get test data from database
#         test = await TestManager.get_test(test_id)
#         if not test:
#             await callback.message.answer(
#                 "❌ Bu test bazada topilmadi!",
#                 reply_markup=get_user_keyboard()
#             )
#             await state.clear()
#             return
#
#         # Calculate results
#         correct_answers_1_35 = test['answers_1_35']
#         correct_count = sum(
#             1 for i in range(35)
#             if i < len(user_answers) and
#             i < len(correct_answers_1_35) and
#             str(user_answers[i]).upper() == str(correct_answers_1_35[i]).upper()
#         )
#         score = round((correct_count / 35) * 100, 2)
#
#         # Check if user already submitted answers
#         existing_submission = await TestManager.get_test_user_data(test_id, user_id)
#         is_test_active = test.get('status', 'inactive') == 'active'
#
#         # Only save if test is active AND no existing submission
#         if is_test_active:
#             if existing_submission:
#                 # User already submitted - don't save again
#                 saved = False
#             else:
#                 # First time submission - save answers
#                 saved = await TestManager.save_user_answers(
#                     test_id=test_id,
#                     user_id=user_id,
#                     user_data=user_data,
#                     answers=user_answers
#                 )
#         else:
#             saved = False
#
#         if not is_test_active:
#             # Prepare and send results
#             results = [
#                 f"{i + 1}. {user_answers[i] if i < len(user_answers) else ''} "
#                 f"{'✅' if i < len(user_answers) and i < len(correct_answers_1_35) and str(user_answers[i]).upper() == str(correct_answers_1_35[i]).upper() else '❌'} "
#                 f"To'g'ri: {correct_answers_1_35[i] if i < len(correct_answers_1_35) else '?'}"
#                 for i in range(35)
#             ]
#         else:
#             # Prepare and send results
#             results = [
#                 f"{i + 1}. {user_answers[i] if i < len(user_answers) else ''} "
#                 for i in range(35)
#             ]
#
#         # Send in chunks
#         chunk_size = 10
#         for i in range(0, len(results), chunk_size):
#             await callback.message.answer("\n".join(results[i:i + chunk_size]))
#
#         # Final message
#         message = (
#             f"📊 Test: {test_id}\n"
#             f"👤 Foydalanuvchi: {user_data['first_name']} {user_data['second_name']}\n"
#             f"✅ To'g'ri: {correct_count}/35\n"
#             f"📈 {score}%\n"
#         )
#
#         if existing_submission:
#             message += "ℹ️ Siz allaqachon bu testda qatnashgansiz! Javoblaringiz yangilanmadi."
#         elif is_test_active and saved:
#             message += "✅ Javoblaringiz saqlandi!"
#         elif is_test_active and not saved:
#             message += "❌ Javoblarni saqlashda xatolik!"
#         else:
#             message += "ℹ️ Test yakunlangan, javoblaringiz saqlanmadi"
#
#         await callback.message.answer(message, reply_markup=get_user_keyboard())
#
#     except Exception as e:
#         logger.error(f"Error submitting answers: {str(e)}")
#         await callback.message.answer(
#             "❌ Javoblarni tekshirishda xatolik yuz berdi. Iltimos, keyinroq urinib ko'ring.",
#             reply_markup=get_user_keyboard()
#         )
#     finally:
#         await state.clear()
#
# # Restart test
# @router.callback_query(F.data == "restart_test")
# async def restart_test(callback: CallbackQuery, state: FSMContext):
#     data = await state.get_data()
#     await state.update_data(current_question=0, user_answers=[''] * 35)
#     await state.set_state(TestTakingStates.answering_questions)
#     await ask_question(callback, state)
#     await callback.answer()
#
#
# # Helper function to get user keyboard
# def get_user_keyboard():
#     return types.ReplyKeyboardMarkup(
#         keyboard=[
#             [types.KeyboardButton(text="📝 Test ishlash")]
#         ],
#         resize_keyboard=True
#     )