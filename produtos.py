from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove

import catalogo
import database

router = Router()


class ProdutoState(StatesGroup):
    criando_nome = State()
    escolhendo_categoria = State()
    escolhendo_produto = State()
    menu_produto = State()
    editando_nome = State()
    editando_categoria = State()
    excluindo = State()


def kb_produtos_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Novo Produto"), KeyboardButton(text="✏️ Editar Produto")],
            [KeyboardButton(text="🗑️ Excluir Produto")],
            [KeyboardButton(text="⬅️ Menu Principal")],
        ],
        resize_keyboard=True,
    )


def _texto_categoria(c):
    """Monta o texto do botão de categoria com ou sem emoji."""
    emoji = c["emoji"] or ""
    nome = c["nome"]
    return f"{emoji} {nome}".strip() if emoji else nome


def kb_categoria_escolha(categorias):
    btns = [[KeyboardButton(text=_texto_categoria(c))] for c in categorias]
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


async def get_dep_context(state: FSMContext):
    data = await state.get_data()
    dep_id = data.get("departamento_id")
    dep_nome = data.get("departamento_nome")
    dep_emoji = data.get("departamento_emoji")
    catalogo_json = data.get("catalogo_json")

    if catalogo_json and not catalogo.CATALOGO:
        catalogo.carregar_catalogo_dep(catalogo_json)

    return dep_id, dep_nome, dep_emoji, catalogo_json


async def get_dep_id(state: FSMContext):
    dep_id, _, _, _ = await get_dep_context(state)
    return dep_id


async def limpar_estado_preservando_departamento(state: FSMContext):
    dep_id, dep_nome, dep_emoji, catalogo_json = await get_dep_context(state)
    await state.clear()
    if dep_id:
        await state.set_data({
            "departamento_id": dep_id,
            "departamento_nome": dep_nome,
            "departamento_emoji": dep_emoji,
            "catalogo_json": catalogo_json,
        })


# ─── MENU PRODUTOS ────────────────────────────────────────────────────────────

@router.message(F.text == "📦 Produtos")
async def menu_produtos(message: types.Message, state: FSMContext):
    dep_id = await get_dep_id(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento primeiro.")
    await message.answer("📦 Menu de Produtos:", reply_markup=kb_produtos_menu())


# ─── CRIAR PRODUTO ────────────────────────────────────────────────────────────

@router.message(F.text == "➕ Novo Produto")
async def novo_produto(message: types.Message, state: FSMContext):
    dep_id = await get_dep_id(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento primeiro.")

    await limpar_estado_preservando_departamento(state)
    await state.set_state(ProdutoState.criando_nome)
    await message.answer("Digite o nome do produto:", reply_markup=ReplyKeyboardRemove())


@router.message(ProdutoState.criando_nome)
async def produto_nome(message: types.Message, state: FSMContext):
    nome = message.text.strip()
    dep_id = await get_dep_id(state)
    if not dep_id:
        await state.clear()
        return await message.answer("Sessão expirada. Envie /start.")

    await state.update_data(produto_nome=nome)

    categorias = await database.listar_categorias(dep_id)

    await state.set_state(ProdutoState.escolhendo_categoria)

    if not categorias:
        return await message.answer(
            f"Nenhuma categoria cadastrada ainda.\n\n"
            f"Deseja salvar *{nome}* sem categoria?",
            reply_markup=kb_categoria_escolha([]),
            parse_mode="Markdown",
        )

    await message.answer(
        f"Selecione a categoria para *{nome}*:",
        reply_markup=kb_categoria_escolha(categorias),
        parse_mode="Markdown",
    )


@router.message(ProdutoState.escolhendo_categoria)
async def produto_categoria(message: types.Message, state: FSMContext):
    dep_id = await get_dep_id(state)
    if not dep_id:
        await state.clear()
        return await message.answer("Sessão expirada. Envie /start.")

    if message.text == "❌ Cancelar":
        await limpar_estado_preservando_departamento(state)
        return await message.answer("Cancelado.", reply_markup=kb_produtos_menu())

    data = await state.get_data()
    nome = data.get("produto_nome")

    cat_id = None

    if message.text != "🚫 Sem Categoria":
        categorias = await database.listar_categorias(dep_id)

        # Monta mapa usando a mesma função _texto_categoria para garantir consistência
        mapa = {_texto_categoria(c): c["id"] for c in categorias}
        # Fallback: só o nome sem emoji
        mapa_simples = {c["nome"]: c["id"] for c in categorias}

        if message.text in mapa:
            cat_id = mapa[message.text]
        elif message.text in mapa_simples:
            cat_id = mapa_simples[message.text]
        else:
            return await message.answer(
                "Categoria não encontrada. Use os botões do teclado.",
                reply_markup=kb_categoria_escolha(categorias),
            )

    ok = await database.criar_produto(dep_id, nome, cat_id)
    await limpar_estado_preservando_departamento(state)

    if ok:
        await message.answer(
            f"✅ Produto *{nome}* cadastrado com sucesso!",
            reply_markup=kb_produtos_menu(),
            parse_mode="Markdown",
        )
    else:
        await message.answer(
            f"⚠️ Já existe um produto chamado *{nome}* neste catálogo.",
            reply_markup=kb_produtos_menu(),
            parse_mode="Markdown",
        )


# ─── EDITAR PRODUTO ───────────────────────────────────────────────────────────

@router.message(F.text == "✏️ Editar Produto")
async def editar_produto(message: types.Message, state: FSMContext):
    dep_id = await get_dep_id(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento primeiro.")

    await limpar_estado_preservando_departamento(state)

    produtos = await database.listar_produtos(dep_id)
    if not produtos:
        return await message.answer("Nenhum produto cadastrado.", reply_markup=kb_produtos_menu())

    await state.set_state(ProdutoState.escolhendo_produto)
    await message.answer("Escolha o produto para editar:", reply_markup=kb_produto_escolha(produtos))


@router.message(ProdutoState.escolhendo_produto)
async def selecionar_produto(message: types.Message, state: FSMContext):
    dep_id = await get_dep_id(state)
    if not dep_id:
        await state.clear()
        return await message.answer("Sessão expirada. Envie /start.")

    if message.text == "❌ Cancelar":
        await limpar_estado_preservando_departamento(state)
        return await message.answer("Cancelado.", reply_markup=kb_produtos_menu())

    produtos = await database.listar_produtos(dep_id)
    mapa = {}
    for p in produtos:
        texto = p["nome"]
        if p["categoria_nome"]:
            texto = f"{p['nome']} ({p['categoria_nome']})"
        mapa[texto] = p

    if message.text not in mapa:
        return await message.answer(
            "Produto não encontrado. Use os botões do teclado.",
            reply_markup=kb_produto_escolha(produtos),
        )

    p = mapa[message.text]
    await state.update_data(prod_id=p["id"], prod_nome=p["nome"])
    await state.set_state(ProdutoState.menu_produto)

    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✏️ Renomear"), KeyboardButton(text="📂 Trocar Categoria")],
            [KeyboardButton(text="🗑️ Excluir")],
            [KeyboardButton(text="⬅️ Voltar"), KeyboardButton(text="❌ Cancelar")],
        ],
        resize_keyboard=True,
    )

    texto_cat = p["categoria_nome"] if p["categoria_nome"] else "Sem categoria"
    await message.answer(
        f"Produto: *{p['nome']}*\nCategoria atual: *{texto_cat}*\n\nO que deseja fazer?",
        reply_markup=kb,
        parse_mode="Markdown",
    )


@router.message(ProdutoState.menu_produto)
async def menu_edicao_produto(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prod_nome = data.get("prod_nome")

    if message.text == "❌ Cancelar":
        await limpar_estado_preservando_departamento(state)
        return await message.answer("Cancelado.", reply_markup=kb_produtos_menu())

    if message.text == "⬅️ Voltar":
        await limpar_estado_preservando_departamento(state)
        return await message.answer("Menu de Produtos:", reply_markup=kb_produtos_menu())

    if message.text == "✏️ Renomear":
        await state.set_state(ProdutoState.editando_nome)
        return await message.answer("Digite o novo nome:", reply_markup=ReplyKeyboardRemove())

    if message.text == "📂 Trocar Categoria":
        dep_id = await get_dep_id(state)
        if not dep_id:
            await state.clear()
            return await message.answer("Sessão expirada. Envie /start.")

        categorias = await database.listar_categorias(dep_id)
        await state.set_state(ProdutoState.editando_categoria)

        if not categorias:
            return await message.answer(
                "Nenhuma categoria cadastrada. Deseja deixar sem categoria?",
                reply_markup=kb_categoria_escolha([]),
            )

        return await message.answer(
            "Escolha a nova categoria:",
            reply_markup=kb_categoria_escolha(categorias),
        )

    if message.text == "🗑️ Excluir":
        await state.set_state(ProdutoState.excluindo)
        return await message.answer(
            f"Confirma excluir *{prod_nome}*?\n\nDigite *SIM* para confirmar.",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove(),
        )

    await message.answer("Use o teclado do bot.")


@router.message(ProdutoState.editando_nome)
async def produto_novo_nome(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prod_id = data.get("prod_id")
    novo_nome = message.text.strip()

    await database.atualizar_produto(prod_id, nome=novo_nome)
    await limpar_estado_preservando_departamento(state)

    await message.answer(
        f"✅ Produto renomeado para *{novo_nome}*.",
        reply_markup=kb_produtos_menu(),
        parse_mode="Markdown",
    )


@router.message(ProdutoState.editando_categoria)
async def produto_nova_categoria(message: types.Message, state: FSMContext):
    dep_id = await get_dep_id(state)
    if not dep_id:
        await state.clear()
        return await message.answer("Sessão expirada. Envie /start.")

    if message.text == "❌ Cancelar":
        await limpar_estado_preservando_departamento(state)
        return await message.answer("Cancelado.", reply_markup=kb_produtos_menu())

    data = await state.get_data()
    prod_id = data.get("prod_id")

    cat_id = None

    if message.text != "🚫 Sem Categoria":
        categorias = await database.listar_categorias(dep_id)
        mapa = {_texto_categoria(c): c["id"] for c in categorias}
        mapa_simples = {c["nome"]: c["id"] for c in categorias}

        if message.text in mapa:
            cat_id = mapa[message.text]
        elif message.text in mapa_simples:
            cat_id = mapa_simples[message.text]
        else:
            return await message.answer(
                "Categoria não encontrada. Use os botões do teclado.",
                reply_markup=kb_categoria_escolha(categorias),
            )

    await database.atualizar_produto(prod_id, cat_id=cat_id)
    await limpar_estado_preservando_departamento(state)

    await message.answer(
        "✅ Categoria do produto atualizada com sucesso!",
        reply_markup=kb_produtos_menu(),
    )


# ─── EXCLUIR PRODUTO ──────────────────────────────────────────────────────────

@router.message(F.text == "🗑️ Excluir Produto")
async def excluir_produto_menu(message: types.Message, state: FSMContext):
    dep_id = await get_dep_id(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento primeiro.")

    await limpar_estado_preservando_departamento(state)

    produtos = await database.listar_produtos(dep_id)
    if not produtos:
        return await message.answer("Nenhum produto cadastrado.", reply_markup=kb_produtos_menu())

    await state.set_state(ProdutoState.escolhendo_produto)
    await message.answer(
        "Qual produto deseja excluir?",
        reply_markup=kb_produto_escolha(produtos),
    )


@router.message(ProdutoState.excluindo)
async def produto_confirmar_exclusao(message: types.Message, state: FSMContext):
    if message.text.strip().lower() != "sim":
        await limpar_estado_preservando_departamento(state)
        return await message.answer("Exclusão cancelada.", reply_markup=kb_produtos_menu())

    data = await state.get_data()
    prod_id = data.get("prod_id")
    prod_nome = data.get("prod_nome")

    await database.deletar_produto(prod_id)
    await limpar_estado_preservando_departamento(state)

    await message.answer(
        f"🗑️ Produto *{prod_nome}* excluído com sucesso.",
        reply_markup=kb_produtos_menu(),
        parse_mode="Markdown",
    )