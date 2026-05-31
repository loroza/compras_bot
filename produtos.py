from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

import database
import catalogo

router = Router()


class ProdutoState(StatesGroup):
    criando_nome = State()
    escolhendo_categoria = State()
    escolhendo_produto = State()
    menu_produto = State()
    editando_nome = State()
    editando_categoria = State()
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


def kb_produtos_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Novo Produto"), KeyboardButton(text="✏️ Editar Produto")],
        [KeyboardButton(text="🗑️ Excluir Produto")],
        [KeyboardButton(text="⬅️ Menu Principal")]
    ], resize_keyboard=True)


def kb_categoria_escolha(categorias):
    btns = [[KeyboardButton(text=f"{c['emoji']} {c['nome']}")] for c in categorias]
    btns.append([KeyboardButton(text="🚫 Sem Categoria")])
    btns.append([KeyboardButton(text="❌ Cancelar")])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)


def kb_produto_escolha(produtos):
    btns = []
    for p in produtos:
        nome = p["nome"]
        if p["categoria_nome"]:
            nome = f"{p['nome']} ({p['categoria_nome']})"
        btns.append([KeyboardButton(text=nome)])
    btns.append([KeyboardButton(text="❌ Cancelar")])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)


async def get_dep_id(state: FSMContext):
    data = await state.get_data()
    return data.get("departamento_id")


@router.message(F.text == "📦 Produtos")
async def menu_produtos(message: types.Message):
    await message.answer("📦 Menu de Produtos:", reply_markup=kb_produtos_menu())


@router.message(F.text == "➕ Novo Produto")
async def novo_produto(message: types.Message, state: FSMContext):
    dep_id = await get_dep_id(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento primeiro.")

    await state.set_state(ProdutoState.criando_nome)
    await message.answer("Digite o nome do produto:", reply_markup=ReplyKeyboardRemove())


@router.message(ProdutoState.criando_nome)
async def produto_nome(message: types.Message, state: FSMContext):
    nome = message.text.strip()
    await state.update_data(produto_nome=nome)

    dep_id = await get_dep_id(state)
    categorias = await database.listar_categorias(dep_id)

    if not categorias:
        await state.update_data(cat_id=None)
        return await state.set_state(ProdutoState.escolhendo_categoria) or await message.answer(
            "Nenhuma categoria cadastrada. O produto será salvo sem categoria?\n"
            "Digite SIM para confirmar ou CANCELAR.",
        )

    await state.set_state(ProdutoState.escolhendo_categoria)
    await message.answer("Escolha a categoria do produto:", reply_markup=kb_categoria_escolha(categorias))


@router.message(ProdutoState.escolhendo_categoria)
async def produto_categoria(message: types.Message, state: FSMContext):
    dep_id = await get_dep_id(state)
    data = await state.get_data()
    nome = data.get("produto_nome")

    if message.text == "❌ Cancelar":
        await state.clear()
        return await message.answer("Cancelado.", reply_markup=kb_produtos_menu())

    categorias = await database.listar_categorias(dep_id)

    if not categorias:
        if message.text.strip().lower() != "sim":
            await state.clear()
            return await message.answer("Cancelado.", reply_markup=kb_produtos_menu())

        ok = await database.criar_produto(dep_id, nome, None)
        await state.clear()
        if ok:
            return await message.answer(f"✅ Produto *{nome}* criado sem categoria.", reply_markup=kb_produtos_menu(), parse_mode="Markdown")
        return await message.answer("⚠️ Já existe um produto com esse nome.", reply_markup=kb_produtos_menu())

    if message.text == "🚫 Sem Categoria":
        cat_id = None
    else:
        mapa = {f"{c['emoji']} {c['nome']}": c["id"] for c in categorias}
        if message.text not in mapa:
            return await message.answer("Escolha uma categoria válida.", reply_markup=kb_categoria_escolha(categorias))
        cat_id = mapa[message.text]

    ok = await database.criar_produto(dep_id, nome, cat_id)
    await state.clear()

    if ok:
        await message.answer(f"✅ Produto *{nome}* criado!", reply_markup=kb_produtos_menu(), parse_mode="Markdown")
    else:
        await message.answer("⚠️ Já existe um produto com esse nome.", reply_markup=kb_produtos_menu())


@router.message(F.text == "✏️ Editar Produto")
async def editar_produto(message: types.Message, state: FSMContext):
    dep_id = await get_dep_id(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento primeiro.")

    produtos = await database.listar_produtos(dep_id)
    if not produtos:
        return await message.answer("Nenhum produto cadastrado.", reply_markup=kb_produtos_menu())

    await state.set_state(ProdutoState.escolhendo_produto)
    await message.answer("Escolha o produto:", reply_markup=kb_produto_escolha(produtos))


@router.message(ProdutoState.escolhendo_produto)
async def selecionar_produto(message: types.Message, state: FSMContext):
    dep_id = await get_dep_id(state)
    if not dep_id:
        await state.clear()
        return await message.answer("Envie /start e escolha um departamento primeiro.")

    if message.text == "❌ Cancelar":
        await state.clear()
        return await message.answer("Cancelado.", reply_markup=kb_produtos_menu())

    produtos = await database.listar_produtos(dep_id)
    mapa = {}
    for p in produtos:
        texto = p["nome"]
        if p["categoria_nome"]:
            texto = f"{p['nome']} ({p['categoria_nome']})"
        mapa[texto] = p

    if message.text not in mapa:
        return await message.answer("Escolha um produto válido.", reply_markup=kb_produto_escolha(produtos))

    p = mapa[message.text]
    await state.update_data(prod_id=p["id"], prod_nome=p["nome"])
    await state.set_state(ProdutoState.menu_produto)

    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="✏️ Renomear"), KeyboardButton(text="📂 Trocar Categoria")],
        [KeyboardButton(text="🗑️ Excluir")],
        [KeyboardButton(text="⬅️ Voltar"), KeyboardButton(text="❌ Cancelar")]
    ], resize_keyboard=True)

    texto_cat = p["categoria_nome"] if p["categoria_nome"] else "Sem categoria"
    await message.answer(
        f"Produto selecionado: *{p['nome']}*\nCategoria atual: *{texto_cat}*",
        reply_markup=kb,
        parse_mode="Markdown"
    )


@router.message(ProdutoState.menu_produto)
async def menu_edicao_produto(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prod_nome = data.get("prod_nome")

    if message.text == "❌ Cancelar":
        await state.clear()
        return await message.answer("Cancelado.", reply_markup=kb_produtos_menu())

    if message.text == "⬅️ Voltar":
        await state.clear()
        return await message.answer("Menu de Produtos:", reply_markup=kb_produtos_menu())

    if message.text == "✏️ Renomear":
        await state.set_state(ProdutoState.editando_nome)
        return await message.answer("Digite o novo nome:", reply_markup=ReplyKeyboardRemove())

    if message.text == "📂 Trocar Categoria":
        dep_id = await get_dep_id(state)
        categorias = await database.listar_categorias(dep_id)
        if not categorias:
            await state.set_state(ProdutoState.editando_categoria)
            return await message.answer(
                "Não existem categorias cadastradas. Digite SIM para deixar sem categoria ou CANCELAR.",
            )

        await state.set_state(ProdutoState.editando_categoria)
        return await message.answer("Escolha a nova categoria:", reply_markup=kb_categoria_escolha(categorias))

    if message.text == "🗑️ Excluir":
        await state.set_state(ProdutoState.excluindo)
        return await message.answer(f"Confirma excluir *{prod_nome}*? Digite SIM para confirmar.", parse_mode="Markdown")

    await message.answer("Use o teclado do bot.")


@router.message(ProdutoState.editando_nome)
async def produto_novo_nome(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prod_id = data.get("prod_id")
    novo_nome = message.text.strip()

    await database.atualizar_produto(prod_id, nome=novo_nome)
    await state.clear()
    await message.answer(f"✅ Produto renomeado para *{novo_nome}*.", reply_markup=kb_produtos_menu(), parse_mode="Markdown")


@router.message(ProdutoState.editando_categoria)
async def produto_nova_categoria(message: types.Message, state: FSMContext):
    dep_id = await get_dep_id(state)
    data = await state.get_data()
    prod_id = data.get("prod_id")

    if message.text == "❌ Cancelar":
        await state.clear()
        return await message.answer("Cancelado.", reply_markup=kb_produtos_menu())

    categorias = await database.listar_categorias(dep_id)

    if not categorias:
        if message.text.strip().lower() != "sim":
            await state.clear()
            return await message.answer("Cancelado.", reply_markup=kb_produtos_menu())

        await database.atualizar_produto(prod_id, cat_id=None)
        await state.clear()
        return await message.answer("✅ Produto atualizado sem categoria.", reply_markup=kb_produtos_menu())

    if message.text == "🚫 Sem Categoria":
        cat_id = None
    else:
        mapa = {f"{c['emoji']} {c['nome']}": c["id"] for c in categorias}
        if message.text not in mapa:
            return await message.answer("Escolha uma categoria válida.", reply_markup=kb_categoria_escolha(categorias))
        cat_id = mapa[message.text]

    await database.atualizar_produto(prod_id, cat_id=cat_id)
    await state.clear()
    await message.answer("✅ Categoria do produto atualizada.", reply_markup=kb_produtos_menu())


@router.message(ProdutoState.excluindo)
async def produto_confirmar_exclusao(message: types.Message, state: FSMContext):
    if message.text.strip().lower() != "sim":
        await state.clear()
        return await message.answer("Exclusão cancelada.", reply_markup=kb_produtos_menu())

    data = await state.get_data()
    prod_id = data.get("prod_id")
    prod_nome = data.get("prod_nome")

    await database.deletar_produto(prod_id)
    await state.clear()
    await message.answer(f"🗑️ Produto *{prod_nome}* excluído.", reply_markup=kb_produtos_menu(), parse_mode="Markdown")