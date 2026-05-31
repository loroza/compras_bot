from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

import database
import catalogo

router = Router()


class CategoriaState(StatesGroup):
    criando_nome = State()
    criando_emoji = State()
    escolhendo_categoria = State()
    menu_categoria = State()
    editando_nome = State()
    editando_emoji = State()
    excluindo = State()


def kb_menu_principal():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🛒 Compras"), KeyboardButton(text="📲 Cadastros")],
        [KeyboardButton(text="🏁 Finalizar")]
    ], resize_keyboard=True)


def kb_menu_cadastros():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🏷️ Categorias"), KeyboardButton(text="📋 Listas")],
        [KeyboardButton(text="📦 Produtos")],
        [KeyboardButton(text="⬅️ Menu Principal")]
    ], resize_keyboard=True)


def kb_categorias_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Nova Categoria"), KeyboardButton(text="✏️ Editar Categoria")],
        [KeyboardButton(text="🗑️ Excluir Categoria")],
        [KeyboardButton(text="⬅️ Menu Principal")]
    ], resize_keyboard=True)


def kb_categoria_escolha(categorias):
    btns = [[KeyboardButton(text=f"{c['emoji']} {c['nome']}")] for c in categorias]
    btns.append([KeyboardButton(text="❌ Cancelar")])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)


async def get_dep_id(state: FSMContext):
    data = await state.get_data()
    return data.get("departamento_id")


@router.message(F.text == "🏷️ Categorias")
async def menu_categorias(message: types.Message):
    await message.answer("🏷️ Menu de Categorias:", reply_markup=kb_categorias_menu())


@router.message(F.text == "➕ Nova Categoria")
async def nova_categoria(message: types.Message, state: FSMContext):
    dep_id = await get_dep_id(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento primeiro.")

    await state.set_state(CategoriaState.criando_nome)
    await message.answer("Digite o nome da categoria:", reply_markup=ReplyKeyboardRemove())


@router.message(CategoriaState.criando_nome)
async def categoria_nome(message: types.Message, state: FSMContext):
    nome = message.text.strip()
    await state.update_data(categoria_nome=nome)
    await state.set_state(CategoriaState.criando_emoji)
    await message.answer("Agora digite o emoji da categoria. Ex: 🥦")


@router.message(CategoriaState.criando_emoji)
async def categoria_emoji(message: types.Message, state: FSMContext):
    dep_id = await get_dep_id(state)
    data = await state.get_data()
    nome = data.get("categoria_nome")
    emoji = message.text.strip() or "🏷️"

    ok = await database.criar_categoria(dep_id, nome, emoji)
    await state.clear()

    if ok:
        await message.answer(f"✅ Categoria *{emoji} {nome}* criada!", reply_markup=kb_categorias_menu(), parse_mode="Markdown")
    else:
        await message.answer("⚠️ Já existe uma categoria com esse nome.", reply_markup=kb_categorias_menu())


@router.message(F.text == "✏️ Editar Categoria")
async def editar_categoria(message: types.Message, state: FSMContext):
    dep_id = await get_dep_id(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento primeiro.")

    categorias = await database.listar_categorias(dep_id)
    if not categorias:
        return await message.answer("Nenhuma categoria cadastrada.", reply_markup=kb_categorias_menu())

    await state.set_state(CategoriaState.escolhendo_categoria)
    await message.answer("Escolha a categoria:", reply_markup=kb_categoria_escolha(categorias))


@router.message(CategoriaState.escolhendo_categoria)
async def selecionar_categoria(message: types.Message, state: FSMContext):
    dep_id = await get_dep_id(state)
    if not dep_id:
        await state.clear()
        return await message.answer("Envie /start e escolha um departamento primeiro.")

    if message.text == "❌ Cancelar":
        await state.clear()
        return await message.answer("Cancelado.", reply_markup=kb_categorias_menu())

    categorias = await database.listar_categorias(dep_id)
    mapa = {f"{c['emoji']} {c['nome']}": c for c in categorias}

    if message.text not in mapa:
        return await message.answer("Selecione uma categoria válida.", reply_markup=kb_categoria_escolha(categorias))

    cat = mapa[message.text]
    await state.update_data(cat_id=cat["id"], cat_nome=cat["nome"], cat_emoji=cat["emoji"])
    await state.set_state(CategoriaState.menu_categoria)

    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="✏️ Renomear"), KeyboardButton(text="🎨 Alterar Emoji")],
        [KeyboardButton(text="🗑️ Excluir")],
        [KeyboardButton(text="⬅️ Voltar"), KeyboardButton(text="❌ Cancelar")]
    ], resize_keyboard=True)

    await message.answer(
        f"Categoria selecionada: *{cat['emoji']} {cat['nome']}*",
        reply_markup=kb,
        parse_mode="Markdown"
    )


@router.message(CategoriaState.menu_categoria)
async def menu_edicao_categoria(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cat_nome = data.get("cat_nome")

    if message.text == "❌ Cancelar":
        await state.clear()
        return await message.answer("Cancelado.", reply_markup=kb_categorias_menu())

    if message.text == "⬅️ Voltar":
        await state.clear()
        return await message.answer("Menu de Categorias:", reply_markup=kb_categorias_menu())

    if message.text == "✏️ Renomear":
        await state.set_state(CategoriaState.editando_nome)
        return await message.answer("Digite o novo nome:", reply_markup=ReplyKeyboardRemove())

    if message.text == "🎨 Alterar Emoji":
        await state.set_state(CategoriaState.editando_emoji)
        return await message.answer("Digite o novo emoji:", reply_markup=ReplyKeyboardRemove())

    if message.text == "🗑️ Excluir":
        await state.set_state(CategoriaState.excluindo)
        return await message.answer(f"Confirma excluir *{cat_nome}*? Digite SIM para confirmar.", parse_mode="Markdown")

    await message.answer("Use o teclado do bot.")


@router.message(CategoriaState.editando_nome)
async def categoria_renomear(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cat_id = data.get("cat_id")
    novo_nome = message.text.strip()

    await database.atualizar_categoria(cat_id, nome=novo_nome)
    await state.clear()
    await message.answer(f"✅ Categoria renomeada para *{novo_nome}*.", reply_markup=kb_categorias_menu(), parse_mode="Markdown")


@router.message(CategoriaState.editando_emoji)
async def categoria_novo_emoji(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cat_id = data.get("cat_id")
    novo_emoji = message.text.strip() or "🏷️"

    await database.atualizar_categoria(cat_id, emoji=novo_emoji)
    await state.clear()
    await message.answer(f"✅ Emoji atualizado para *{novo_emoji}*.", reply_markup=kb_categorias_menu(), parse_mode="Markdown")


@router.message(CategoriaState.excluindo)
async def categoria_confirmar_exclusao(message: types.Message, state: FSMContext):
    if message.text.strip().lower() != "sim":
        await state.clear()
        return await message.answer("Exclusão cancelada.", reply_markup=kb_categorias_menu())

    data = await state.get_data()
    cat_id = data.get("cat_id")
    cat_nome = data.get("cat_nome")

    await database.deletar_categoria(cat_id)
    await state.clear()
    await message.answer(f"🗑️ Categoria *{cat_nome}* excluída.", reply_markup=kb_categorias_menu(), parse_mode="Markdown")