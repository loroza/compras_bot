# orcamentos.py
import time
import os
import traceback
from aiogram import Router, types, F
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import database  # usa as funções de conexão e helpers já existentes

router = Router()

# --- Estados ---
class OrcState(StatesGroup):
    menu = State()

    # criação novo orçamento
    novo_tipo_loja = State()
    novo_nome_loja = State()
    novo_descricao = State()
    novo_link = State()
    novo_selecionar_lista = State()
    novo_selecionar_produto = State()
    novo_qtd = State()
    novo_valor = State()
    novo_confirmar = State()

    # editar orçamento
    editar_selecionar_orc = State()
    editar_menu = State()
    editar_incluir_produto = State()
    editar_incluir_produto_qtd = State()
    editar_incluir_produto_valor = State()
    editar_excluir_selecionar_item = State()
    editar_editar_selecionar_item = State()
    editar_editar_nova_qtd = State()
    editar_editar_novo_valor = State()

    # histórico
    historico = State()
    historico_detalhe = State()


# --- Helpers / Keyboards ---
def kb_orcamentos_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Novo orçamento")],
            [KeyboardButton(text="✏️ Editar orçamento"), KeyboardButton(text="🗂️ Histórico")],
            [KeyboardButton(text="⬅️ Voltar")]
        ],
        resize_keyboard=True,
    )


def kb_tipoloja():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏬 Física"), KeyboardButton(text="🛒 E-commerce")],
            [KeyboardButton(text="⬅️ Voltar")]
        ],
        resize_keyboard=True,
    )


def kb_confirmar_cancelar(voltar_text="⬅️ Voltar"):
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Finalizar"), KeyboardButton(text="➕ Adicionar outro item")],
            [KeyboardButton(text=voltar_text)]
        ],
        resize_keyboard=True,
    )


def kb_voltar():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⬅️ Voltar")]],
        resize_keyboard=True,
    )


def parse_decimal(text: str) -> float:
    """Tolerant decimal parser (mesma lógica do main)."""
    s = str(text).strip()
    import re
    s = re.sub(r"[^\d,.\-]", "", s)
    if s == "" or s in (".", ",", "-", "-.", "-,"):
        raise ValueError("valor inválido")
    if s.count(".") > 0 and s.count(",") > 0:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(",") > 0 and s.count(".") == 0:
        s = s.replace(",", ".")
    return float(s)


# --- Helpers para labels (tolerantes) ---
def build_product_label(prod):
    """
    Gera label no formato:
    Categoria > Subcategoria > Produto — Unidade — R$X.XX
    Aceita:
      - prod: dict com keys 'categoria', 'subcategoria', 'nome'/'produto_nome'/'item_nome', 'unidade', 'valor_unitario'
      - prod: string -> retorna a string
    """
    if isinstance(prod, str):
        return prod
    # tentar múltiplas chaves possíveis para nome
    nome = prod.get("nome") or prod.get("produto_nome") or prod.get("item_nome") or prod.get("nome_produto") or ""
    categoria = prod.get("categoria") or prod.get("cat") or ""
    sub = prod.get("subcategoria") or prod.get("sub") or ""
    unidade = prod.get("unidade") or prod.get("un") or ""
    valor = prod.get("valor_unitario")
    valor_num = 0.0
    try:
        if valor is not None:
            valor_num = float(valor)
    except Exception:
        valor_num = 0.0

    parts = []
    if categoria:
        parts.append(categoria)
    if sub:
        parts.append(sub)
    if nome:
        parts.append(nome)
    label = " > ".join(parts) if parts else nome or str(prod)
    if unidade:
        label = f"{label} — {unidade}"
    label = f"{label} — R${valor_num:.2f}"
    return label


def build_orc_item_label(item_row):
    """
    Gera label para itens já adicionados ao orçamento:
    Categoria > Subcategoria > Produto — Unidade — R$X.XX
    Fallback: ID:XX | produto — R$X.XX
    """
    # item_row pode ser dict com keys item_nome, categoria, subcategoria, unidade, valor_unitario, id
    try:
        nome = item_row.get("item_nome") or item_row.get("nome") or ""
        categoria = item_row.get("categoria") or ""
        sub = item_row.get("subcategoria") or ""
        unidade = item_row.get("unidade") or ""
        valor = item_row.get("valor_unitario") or 0.0
        id_ = item_row.get("id")
        # montar partes
        parts = []
        if categoria:
            parts.append(categoria)
        if sub:
            parts.append(sub)
        if nome:
            parts.append(nome)
        label_main = " > ".join(parts) if parts else nome or ""
        if unidade:
            label_main = f"{label_main} — {unidade}"
        label = f"{label_main} — R${float(valor):.2f}"
        if id_ is not None:
            label = f"ID:{id_} | {label}"
        return label
    except Exception:
        # fallback simples
        id_ = item_row.get("id") if isinstance(item_row, dict) else None
        nome = item_row.get("item_nome") if isinstance(item_row, dict) else str(item_row)
        valor = item_row.get("valor_unitario") if isinstance(item_row, dict) else 0.0
        if id_:
            return f"ID:{id_} | {nome} — R${float(valor):.2f}"
        return f"{nome} — R${float(valor):.2f}"


# --- DB: garante tabelas/colunas necessárias (idempotente) ---
async def ensure_tables():
    conn = await database.get_conn()
    try:
        # cria tabela orcamentos se não existir, e garante colunas
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS orcamentos (
                id SERIAL PRIMARY KEY
            );
        """)
        await conn.execute("ALTER TABLE orcamentos ADD COLUMN IF NOT EXISTS departamento_id INTEGER REFERENCES departamentos(id) ON DELETE CASCADE;")
        await conn.execute("ALTER TABLE orcamentos ADD COLUMN IF NOT EXISTS tipo_loja TEXT;")
        await conn.execute("ALTER TABLE orcamentos ADD COLUMN IF NOT EXISTS nome_loja TEXT;")
        await conn.execute("ALTER TABLE orcamentos ADD COLUMN IF NOT EXISTS descricao TEXT;")
        await conn.execute("ALTER TABLE orcamentos ADD COLUMN IF NOT EXISTS link TEXT;")
        await conn.execute("ALTER TABLE orcamentos ADD COLUMN IF NOT EXISTS lista_id INTEGER;")
        await conn.execute("ALTER TABLE orcamentos ADD COLUMN IF NOT EXISTS criado_por BIGINT;")
        await conn.execute("ALTER TABLE orcamentos ADD COLUMN IF NOT EXISTS criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP;")

        # garante a tabela de itens
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS orcamento_itens (
                id SERIAL PRIMARY KEY
            );
        """)
        await conn.execute("ALTER TABLE orcamento_itens ADD COLUMN IF NOT EXISTS orcamento_id INTEGER REFERENCES orcamentos(id) ON DELETE CASCADE;")
        await conn.execute("ALTER TABLE orcamento_itens ADD COLUMN IF NOT EXISTS item_nome TEXT;")
        await conn.execute("ALTER TABLE orcamento_itens ADD COLUMN IF NOT EXISTS quantidade REAL;")
        await conn.execute("ALTER TABLE orcamento_itens ADD COLUMN IF NOT EXISTS valor_unitario REAL;")
    finally:
        await conn.close()


# --- DB helpers específicos de orcamentos ---
async def criar_orcamento(dep_id, tipo_loja, nome_loja, descricao, link, lista_id, criado_por, itens):
    """
    itens: lista de dicts {'item_nome','quantidade','valor_unitario'}
    Retorna id do orçamento criado.
    """
    conn = await database.get_conn()
    try:
        orc_id = await conn.fetchval(
            """
            INSERT INTO orcamentos
            (departamento_id, tipo_loja, nome_loja, descricao, link, lista_id, criado_por)
            VALUES ($1,$2,$3,$4,$5,$6,$7)
            RETURNING id
            """,
            dep_id, tipo_loja, nome_loja, descricao, link, lista_id, criado_por
        )
        for it in itens:
            await conn.execute(
                """
                INSERT INTO orcamento_itens (orcamento_id, item_nome, quantidade, valor_unitario)
                VALUES ($1,$2,$3,$4)
                """,
                orc_id, it.get("item_nome"), it.get("quantidade", 0), it.get("valor_unitario", 0)
            )
        return orc_id
    finally:
        await conn.close()


async def listar_orcamentos(dep_id):
    conn = await database.get_conn()
    try:
        rows = await conn.fetch(
            """
            SELECT id, nome_loja, tipo_loja, descricao, link, lista_id, criado_por, criado_em
            FROM orcamentos
            WHERE departamento_id = $1
            ORDER BY criado_em DESC
            """,
            dep_id
        )
        return rows
    finally:
        await conn.close()


async def listar_itens_orcamento(orc_id):
    conn = await database.get_conn()
    try:
        rows = await conn.fetch(
            """
            SELECT id, item_nome, quantidade, valor_unitario
            FROM orcamento_itens
            WHERE orcamento_id = $1
            ORDER BY id
            """,
            orc_id
        )
        # rows podem conter colunas extras (categoria, subcategoria, unidade) dependendo do schema
        return rows
    finally:
        await conn.close()


async def adicionar_item_orc(orc_id, item_nome, quantidade, valor_unitario):
    conn = await database.get_conn()
    try:
        await conn.execute(
            """
            INSERT INTO orcamento_itens (orcamento_id, item_nome, quantidade, valor_unitario)
            VALUES ($1,$2,$3,$4)
            """,
            orc_id, item_nome, quantidade, valor_unitario
        )
    finally:
        await conn.close()


async def excluir_item_orc_por_id(item_id):
    conn = await database.get_conn()
    try:
        await conn.execute("DELETE FROM orcamento_itens WHERE id = $1", item_id)
    finally:
        await conn.close()


async def contar_itens_orcamento(orc_id):
    conn = await database.get_conn()
    try:
        cnt = await conn.fetchval("SELECT COUNT(*) FROM orcamento_itens WHERE orcamento_id = $1", orc_id)
        return cnt
    finally:
        await conn.close()


async def deletar_orcamento(orc_id):
    conn = await database.get_conn()
    try:
        await conn.execute("DELETE FROM orcamentos WHERE id = $1", orc_id)
    finally:
        await conn.close()


# --- HANDLERS ---


@router.message(F.text == "📊 Orçamentos")
async def abrir_orcamentos_menu(message: types.Message, state: FSMContext):
    dep_id = (await state.get_data()).get("departamento_id")
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento antes de acessar orçamentos.")
    # garante tabelas
    try:
        await ensure_tables()
    except Exception:
        traceback.print_exc()
    await state.set_state(OrcState.menu)
    await message.answer("📊 Menu de Orçamentos:", reply_markup=kb_orcamentos_menu())


# Voltar
@router.message(OrcState.menu, F.text == "⬅️ Voltar")
async def orc_voltar_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Voltando...", reply_markup=ReplyKeyboardRemove())


# ─── Novo orçamento ───
@router.message(OrcState.menu, F.text == "➕ Novo orçamento")
async def orc_novo_inicio(message: types.Message, state: FSMContext):
    await state.set_state(OrcState.novo_tipo_loja)
    await message.answer("Selecione o tipo de loja:", reply_markup=kb_tipoloja())


@router.message(OrcState.novo_tipo_loja)
async def orc_novo_tipo_loja_handler(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Voltar":
        await state.set_state(OrcState.menu)
        return await message.answer("📊 Menu de Orçamentos:", reply_markup=kb_orcamentos_menu())
    tipo = "Física" if message.text.startswith("🏬") or message.text == "Física" else "E-commerce"
    await state.update_data(novo_tipo_loja=tipo, novo_itens=[])
    await state.set_state(OrcState.novo_nome_loja)
    await message.answer("Nome da loja do orçamento:", reply_markup=ReplyKeyboardRemove())


@router.message(OrcState.novo_nome_loja)
async def orc_novo_nome_store(message: types.Message, state: FSMContext):
    nome = message.text.strip()
    if not nome:
        return await message.answer("Nome inválido. Digite o nome da loja.")
    await state.update_data(novo_nome_loja=nome)
    await state.set_state(OrcState.novo_descricao)
    await message.answer("Descrição do orçamento (pode ser uma frase curta).", reply_markup=kb_voltar())


@router.message(OrcState.novo_descricao)
async def orc_novo_descricao_handler(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Voltar":
        await state.set_state(OrcState.novo_nome_loja)
        return await message.answer("Nome da loja do orçamento:", reply_markup=ReplyKeyboardRemove())
    desc = message.text.strip()
    await state.update_data(novo_descricao=desc)
    data = await state.get_data()
    tipo = data.get("novo_tipo_loja")
    if tipo == "E-commerce":
        await state.set_state(OrcState.novo_link)
        return await message.answer("Informe o link do site da loja (ou digite '-' se não tiver):", reply_markup=kb_voltar())
    else:
        # pular link
        await state.set_state(OrcState.novo_selecionar_lista)
        return await orc_novo_listas_prompt(message, state)


@router.message(OrcState.novo_link)
async def orc_novo_link_handler(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Voltar":
        await state.set_state(OrcState.novo_descricao)
        return await message.answer("Descrição do orçamento (pode ser uma frase curta).", reply_markup=kb_voltar())
    link = message.text.strip()
    await state.update_data(novo_link=link)
    await state.set_state(OrcState.novo_selecionar_lista)
    await orc_novo_listas_prompt(message, state)


async def orc_novo_listas_prompt(message: types.Message, state: FSMContext):
    data = await state.get_data()
    dep_id = data.get("departamento_id")
    if not dep_id:
        # fallback: tentar novo lookup
        dep_id = (await state.get_data()).get("departamento_id")
    if not dep_id:
        return await message.answer("Erro interno: departamento não selecionado.")
    listas = await database.pegar_listas_disponiveis(dep_id)
    if not listas:
        await state.set_state(OrcState.menu)
        return await message.answer("Nenhuma lista disponível para selecionar. Crie uma lista antes.", reply_markup=kb_orcamentos_menu())

    btns = [[KeyboardButton(text=l["nome"])] for l in listas]
    btns.append([KeyboardButton(text="⬅️ Voltar")])
    kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)
    await state.set_state(OrcState.novo_selecionar_lista)
    await state.update_data(novo_listas_objs={l["nome"]: l["id"] for l in listas})
    await message.answer("Selecione a lista de compra que deseja usar para este orçamento:", reply_markup=kb)


@router.message(OrcState.novo_selecionar_lista)
async def orc_novo_selecionar_lista_handler(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Voltar":
        await state.set_state(OrcState.novo_descricao)
        return await message.answer("Descrição do orçamento (pode ser uma frase curta).", reply_markup=kb_voltar())

    data = await state.get_data()
    map_listas = data.get("novo_listas_objs", {})
    lista_nome = message.text.strip()
    lista_id = map_listas.get(lista_nome)
    if not lista_id:
        return await message.answer("Selecione uma lista válida.")
    await state.update_data(novo_lista_id=lista_id, novo_lista_nome=lista_nome)
    # agora pedir produto da lista
    itens = await database.pegar_itens_da_lista(lista_id)
    if not itens:
        return await message.answer("A lista selecionada não contém itens. Use outra lista ou adicione itens.", reply_markup=kb_voltar())
    # montar keyboard de produtos (formato hierárquico se possível)
    btns = []
    prod_map = {}
    for i in itens:
        label = build_product_label(i)
        btns.append([KeyboardButton(text=label)])
        # mapa guarda, preferindo um id quando existir
        prod_key = None
        if isinstance(i, dict):
            prod_key = i.get("id") or i.get("produto_id") or i.get("produto") or i.get("nome") or i.get("item_nome")
        else:
            prod_key = i
        prod_map[label] = prod_key
    btns.append([KeyboardButton(text="⬅️ Voltar")])
    kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)
    await state.set_state(OrcState.novo_selecionar_produto)
    await state.update_data(novo_produtos_map=prod_map)
    await message.answer("Selecione um produto da lista para adicionar ao orçamento (categoria > subcategoria > produto > unidade > valor):", reply_markup=kb)


@router.message(OrcState.novo_selecionar_produto)
async def orc_novo_produto_handler(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Voltar":
        await state.set_state(OrcState.novo_selecionar_lista)
        return await orc_novo_listas_prompt(message, state)
    data = await state.get_data()
    prod_map = data.get("novo_produtos_map", {})
    chave = message.text.strip()
    produto_key = prod_map.get(chave)
    if not produto_key:
        # se não encontrou por mapa, tentar aceitar texto simples (compatibilidade)
        produto_key = chave
    # armazenar produto temporário (armazenamos o label para preservar info exibida)
    await state.update_data(novo_produto_label=chave, novo_produto=produto_key)
    await state.set_state(OrcState.novo_qtd)
    await message.answer(f"Quantidade para {chave} (ex: 1, 1.5, 2):", reply_markup=ReplyKeyboardRemove())


@router.message(OrcState.novo_qtd)
async def orc_novo_qtd_handler(message: types.Message, state: FSMContext):
    try:
        qtd = parse_decimal(message.text)
    except Exception:
        return await message.answer("Quantidade inválida. Digite um número válido.")
    await state.update_data(novo_qtd=qtd)
    await state.set_state(OrcState.novo_valor)
    await message.answer("Valor unitário (ex: 5.50):")


@router.message(OrcState.novo_valor)
async def orc_novo_valor_handler(message: types.Message, state: FSMContext):
    try:
        valor = parse_decimal(message.text)
    except Exception:
        return await message.answer("Valor inválido. Digite um número válido.")
    data = await state.get_data()
    produto_label = data.get("novo_produto_label") or data.get("novo_produto")
    lista_itens = data.get("novo_itens", [])
    # Guardar item com item_nome proveniente do label (compatível com DB existente)
    lista_itens.append({"item_nome": produto_label, "quantidade": data.get("novo_qtd", 1), "valor_unitario": valor})
    await state.update_data(novo_itens=lista_itens)
    # oferecer adicionar mais ou finalizar
    await state.set_state(OrcState.novo_confirmar)
    texto = "Item adicionado:\n"
    texto += f"• {produto_label} — {data.get('novo_qtd', 1)} x R${valor:.2f}\n\n"
    texto += f"Itens até agora: {len(lista_itens)}\n"
    await message.answer(texto, reply_markup=kb_confirmar_cancelar())


@router.message(OrcState.novo_confirmar)
async def orc_novo_confirmar_handler(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Voltar":
        # volta para seleção de lista
        await state.set_state(OrcState.novo_selecionar_lista)
        return await orc_novo_listas_prompt(message, state)
    if message.text == "➕ Adicionar outro item":
        # voltar para seleção de produto (usar a mesma lista)
        data = await state.get_data()
        lista_id = data.get("novo_lista_id")
        itens = await database.pegar_itens_da_lista(lista_id)
        if not itens:
            return await message.answer("Lista vazia.")
        btns = []
        prod_map = {}
        for i in itens:
            label = build_product_label(i)
            btns.append([KeyboardButton(text=label)])
            prod_key = i.get("id") if isinstance(i, dict) else i
            prod_map[label] = prod_key
        btns.append([KeyboardButton(text="⬅️ Voltar")])
        kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)
        await state.set_state(OrcState.novo_selecionar_produto)
        await state.update_data(novo_produtos_map=prod_map)
        return await message.answer("Selecione produto:", reply_markup=kb)

    # Finalizar
    if message.text == "✅ Finalizar":
        data = await state.get_data()
        dep_id = data.get("departamento_id")
        if not dep_id:
            return await message.answer("Erro interno: departamento não encontrado.")
        tipo = data.get("novo_tipo_loja")
        nome_loja = data.get("novo_nome_loja")
        descricao = data.get("novo_descricao")
        link = data.get("novo_link", None)
        lista_id = data.get("novo_lista_id")
        itens = data.get("novo_itens", [])
        criado_por = message.from_user.id

        if not itens:
            return await message.answer("Orçamento precisa de ao menos um item. Adicione itens antes de finalizar.")

        try:
            orc_id = await criar_orcamento(dep_id, tipo, nome_loja, descricao, link, lista_id, criado_por, itens)
        except Exception:
            traceback.print_exc()
            return await message.answer("Erro ao salvar orçamento no banco. Tente novamente.")

        await state.set_state(OrcState.menu)
        await state.update_data({"ultimo_orc_criado": orc_id})
        await message.answer(f"✅ Orçamento criado (id={orc_id}) com {len(itens)} itens.", reply_markup=kb_orcamentos_menu())
        return

    # qualquer outro texto -> ignorar
    return await message.answer("Use os botões para finalizar ou adicionar mais itens.", reply_markup=kb_confirmar_cancelar())


# ─── Editar orçamento ───
@router.message(OrcState.menu, F.text == "✏️ Editar orçamento")
async def orc_editar_inicio(message: types.Message, state: FSMContext):
    dep_id = (await state.get_data()).get("departamento_id")
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento antes.")
    orcs = await listar_orcamentos(dep_id)
    if not orcs:
        return await message.answer("Nenhum orçamento encontrado.", reply_markup=kb_orcamentos_menu())
    btns = []
    map_orcs = {}
    for o in orcs:
        nome_loja = o.get("nome_loja") or o.get("nome") or "—"
        tipo = o.get("tipo_loja") or "—"
        label = f"{o['id']} — {nome_loja} ({tipo})"
        btns.append([KeyboardButton(text=label)])
        map_orcs[label] = o["id"]
    btns.append([KeyboardButton(text="⬅️ Voltar")])
    kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)
    await state.set_state(OrcState.editar_selecionar_orc)
    await state.update_data(editar_orcs_map=map_orcs)
    await message.answer("Selecione o orçamento que deseja editar:", reply_markup=kb)


@router.message(OrcState.editar_selecionar_orc)
async def orc_editar_selecionar_handler(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Voltar":
        await state.set_state(OrcState.menu)
        return await message.answer("📊 Menu de Orçamentos:", reply_markup=kb_orcamentos_menu())
    data = await state.get_data()
    map_orcs = data.get("editar_orcs_map", {})
    chave = message.text.strip()
    orc_id = map_orcs.get(chave)
    if not orc_id:
        return await message.answer("Selecione um orçamento válido.")
    # guardar seleção
    await state.update_data(editar_orc_id=orc_id)
    # mostrar menu de edição
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Incluir item"), KeyboardButton(text="🗑️ Excluir item")],
            [KeyboardButton(text="✏️ Editar item")],
            [KeyboardButton(text="⬅️ Voltar")]
        ],
        resize_keyboard=True,
    )
    await state.set_state(OrcState.editar_menu)
    await message.answer("Escolha ação de edição:", reply_markup=kb)


@router.message(OrcState.editar_menu)
async def orc_editar_menu_handler(message: types.Message, state: FSMContext):
    text = message.text
    if text == "⬅️ Voltar":
        await state.set_state(OrcState.menu)
        return await message.answer("📊 Menu de Orçamentos:", reply_markup=kb_orcamentos_menu())
    orc_id = (await state.get_data()).get("editar_orc_id")
    if text == "➕ Incluir item":
        # selecionar produto a partir das listas do departamento
        dep_id = (await state.get_data()).get("departamento_id")
        listas = await database.pegar_listas_disponiveis(dep_id)
        if not listas:
            return await message.answer("Nenhuma lista disponível para selecionar.")
        btns = []
        prod_map = {}
        for l in listas:
            # sempre mostrar as listas para o usuário escolher primeiro
            btns.append([KeyboardButton(text=l["nome"])])
        btns.append([KeyboardButton(text="⬅️ Voltar")])
        kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)
        await state.set_state(OrcState.editar_incluir_produto)
        await state.update_data(editar_map_listas={l["nome"]: l["id"] for l in listas})
        return await message.answer("Selecione a lista que contém o produto a incluir:", reply_markup=kb)

    if text == "🗑️ Excluir item":
        itens = await listar_itens_orcamento(orc_id)
        if not itens:
            return await message.answer("Orçamento não possui itens.")
        btns = []
        excluir_map = {}
        for i in itens:
            label = build_orc_item_label(i)
            btns.append([KeyboardButton(text=label)])
            excluir_map[label] = i["id"]
        btns.append([KeyboardButton(text="⬅️ Voltar")])
        kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)
        await state.set_state(OrcState.editar_excluir_selecionar_item)
        await state.update_data(editar_excluir_map=excluir_map)
        return await message.answer("Selecione o produto cadastrado no orçamento para excluir (categoria > subcategoria > produto > unidade > valor):", reply_markup=kb)

    if text == "✏️ Editar item":
        itens = await listar_itens_orcamento(orc_id)
        if not itens:
            return await message.answer("Orçamento não possui itens.")
        btns = []
        editar_map = {}
        for i in itens:
            label = build_orc_item_label(i)
            btns.append([KeyboardButton(text=label)])
            editar_map[label] = i["id"]
        btns.append([KeyboardButton(text="⬅️ Voltar")])
        kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)
        await state.set_state(OrcState.editar_editar_selecionar_item)
        await state.update_data(editar_editar_map=editar_map)
        return await message.answer("Selecione o produto cadastrado no orçamento para editar (categoria > subcategoria > produto > unidade > valor):", reply_markup=kb)

    return await message.answer("Escolha válida: use os botões.")


@router.message(OrcState.editar_incluir_produto)
async def orc_editar_incluir_produto_handler(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Voltar":
        await state.set_state(OrcState.editar_menu)
        return await message.answer("Voltando ao menu de edição.")
    data = await state.get_data()
    map_listas = data.get("editar_map_listas", {})
    lista_id = map_listas.get(message.text.strip())
    if not lista_id:
        return await message.answer("Selecione uma lista válida.")
    # escolher produto da lista
    itens = await database.pegar_itens_da_lista(lista_id)
    if not itens:
        return await message.answer("Lista vazia.")
    btns = []
    prod_map = {}
    for i in itens:
        label = build_product_label(i)
        btns.append([KeyboardButton(text=label)])
        prod_key = i.get("id") if isinstance(i, dict) else i
        prod_map[label] = prod_key
    btns.append([KeyboardButton(text="⬅️ Voltar")])
    kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)
    await state.update_data(editar_incluir_lista_id=lista_id, editar_incluir_produtos_map=prod_map)
    await state.set_state(OrcState.editar_incluir_produto_qtd)
    await message.answer("Selecione o produto para incluir (categoria > subcategoria > produto > unidade > valor):", reply_markup=kb)


@router.message(OrcState.editar_incluir_produto_qtd)
async def orc_editar_incluir_produto_qtd_handler(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Voltar":
        await state.set_state(OrcState.editar_menu)
        return await message.answer("Voltando ao menu de edição.")
    # o texto pode ser o label do produto
    data = await state.get_data()
    prod_map = data.get("editar_incluir_produtos_map", {})
    chosen_label = message.text.strip()
    prod_key = prod_map.get(chosen_label)
    # se o usuário está respondendo quantidade em vez do produto, detectar e aceitar
    if prod_key is None:
        # considerar que foi escolhido um produto anteriormente (estado deveria ter sido salvo)
        # para simplicidade, aceitar o texto como produto label mesmo
        await state.update_data(editar_incluir_produto=chosen_label, editar_incluir_qtd=None)
        await state.set_state(OrcState.editar_incluir_produto_valor)
        return await message.answer(f"Quantidade para {chosen_label}:", reply_markup=ReplyKeyboardRemove())

    # se chegou aqui, o usuário clicou no produto -> pedir quantidade
    await state.update_data(editar_incluir_produto=chosen_label, editar_incluir_qtd=None)
    await state.set_state(OrcState.editar_incluir_produto_valor)
    await message.answer(f"Quantidade para {chosen_label}:", reply_markup=ReplyKeyboardRemove())


@router.message(OrcState.editar_incluir_produto_valor)
async def orc_editar_incluir_produto_valor_handler(message: types.Message, state: FSMContext):
    # primeiro recebemos quantidade (se for numérico) ou tratamos se usuário enviar valor primeiro por engano
    data = await state.get_data()
    if data.get("editar_incluir_qtd") is None:
        # esperamos quantidade
        try:
            qtd = parse_decimal(message.text)
        except Exception:
            return await message.answer("Quantidade inválida. Digite um número válido.")
        await state.update_data(editar_incluir_qtd=qtd)
        await message.answer("Agora digite o valor unitário (ex: 5.50):")
        return

    # se já temos quantidade, agora ler valor
    try:
        valor = parse_decimal(message.text)
    except Exception:
        return await message.answer("Valor inválido. Digite novamente.")
    data = await state.get_data()
    produto_label = data.get("editar_incluir_produto")
    qtd = data.get("editar_incluir_qtd", 1)
    orc_id = data.get("editar_orc_id")
    try:
        await adicionar_item_orc(orc_id, produto_label, qtd, valor)
    except Exception:
        traceback.print_exc()
        return await message.answer("Erro ao adicionar item. Tente novamente.")
    # limpar campos temporários relacionados à inclusão
    await state.update_data(editar_incluir_produto=None, editar_incluir_qtd=None, editar_incluir_lista_id=None, editar_incluir_produtos_map=None)
    # após incluir, mostrar itens atualizados (conforme fluxograma, mostrar itens novamente)
    itens = await listar_itens_orcamento(orc_id)
    texto = "Itens do orçamento (atualizado):\n"
    for it in itens:
        q = it.get("quantidade") or 0
        v = it.get("valor_unitario") or 0
        texto += f"• {build_orc_item_label(it)}\n"
    await state.set_state(OrcState.editar_menu)
    return await message.answer("Item adicionado ao orçamento.\n\n" + texto, reply_markup=ReplyKeyboardRemove())


@router.message(OrcState.editar_excluir_selecionar_item)
async def orc_editar_excluir_item_handler(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Voltar":
        await state.set_state(OrcState.editar_menu)
        return await message.answer("Voltando ao menu de edição.")
    data = await state.get_data()
    map_items = data.get("editar_excluir_map", {})
    chave = message.text.strip()
    item_id = map_items.get(chave)
    if not item_id:
        return await message.answer("Selecione um item válido usando o teclado do bot.")
    # pegar orc_id e deletar
    orc_id = data.get("editar_orc_id")
    try:
        await excluir_item_orc_por_id(item_id)
    except Exception:
        traceback.print_exc()
        return await message.answer("Erro ao excluir item. Tente novamente.")
    # verificar se ainda existem itens
    try:
        cnt = await contar_itens_orcamento(orc_id)
    except Exception:
        traceback.print_exc()
        cnt = 0
    if cnt == 0:
        try:
            await deletar_orcamento(orc_id)
        except Exception:
            traceback.print_exc()
        await state.set_state(OrcState.menu)
        return await message.answer("✅ Item excluído. Orçamento ficou vazio e foi apagado.", reply_markup=kb_orcamentos_menu())
    # se ainda há itens, mostrar lista atualizada
    itens = await listar_itens_orcamento(orc_id)
    texto = "Itens do orçamento (atualizado):\n"
    for it in itens:
        texto += f"• {build_orc_item_label(it)}\n"
    await state.set_state(OrcState.editar_menu)
    return await message.answer("✅ Item excluído com sucesso.\n\n" + texto, reply_markup=ReplyKeyboardRemove())


@router.message(OrcState.editar_editar_selecionar_item)
async def orc_editar_editar_selecionar_item_handler(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Voltar":
        await state.set_state(OrcState.editar_menu)
        return await message.answer("Voltando ao menu de edição.")
    data = await state.get_data()
    map_items = data.get("editar_editar_map", {})
    chave = message.text.strip()
    item_id = map_items.get(chave)
    if not item_id:
        return await message.answer("Selecione um item válido usando o teclado do bot.")
    await state.update_data(editar_item_id=item_id)
    await state.set_state(OrcState.editar_editar_nova_qtd)
    await message.answer("Digite a nova quantidade (ou mantenha o mesmo número):", reply_markup=ReplyKeyboardRemove())


@router.message(OrcState.editar_editar_nova_qtd)
async def orc_editar_editar_nova_qtd_handler(message: types.Message, state: FSMContext):
    try:
        qtd = parse_decimal(message.text)
    except Exception:
        return await message.answer("Quantidade inválida.")
    await state.update_data(editar_item_nova_qtd=qtd)
    await state.set_state(OrcState.editar_editar_novo_valor)
    await message.answer("Digite o novo valor unitário:")


@router.message(OrcState.editar_editar_novo_valor)
async def orc_editar_editar_novo_valor_handler(message: types.Message, state: FSMContext):
    try:
        valor = parse_decimal(message.text)
    except Exception:
        return await message.answer("Valor inválido.")
    data = await state.get_data()
    item_id = data.get("editar_item_id")
    nova_qtd = data.get("editar_item_nova_qtd", 1)
    conn = await database.get_conn()
    try:
        await conn.execute(
            "UPDATE orcamento_itens SET quantidade = $1, valor_unitario = $2 WHERE id = $3",
            nova_qtd, valor, item_id
        )
    finally:
        await conn.close()
    # após editar, mostrar itens atualizados (conforme fluxograma)
    orc_id = data.get("editar_orc_id")
    itens = await listar_itens_orcamento(orc_id)
    texto = "Itens do orçamento (atualizado):\n"
    for it in itens:
        texto += f"• {build_orc_item_label(it)}\n"
    await state.set_state(OrcState.editar_menu)
    return await message.answer("Item atualizado com sucesso.\n\n" + texto, reply_markup=ReplyKeyboardRemove())


# ─── Histórico de orçamentos ───
@router.message(OrcState.menu, F.text == "🗂️ Histórico")
async def orc_historico_inicio(message: types.Message, state: FSMContext):
    dep_id = (await state.get_data()).get("departamento_id")
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento antes.")
    orcs = await listar_orcamentos(dep_id)
    if not orcs:
        return await message.answer("Nenhum orçamento encontrado.", reply_markup=kb_orcamentos_menu())
    btns = []
    map_orcs = {}
    for o in orcs:
        nome_loja = o.get("nome_loja") or o.get("nome") or "—"
        tipo = o.get("tipo_loja") or "—"
        label = f"{o['id']} — {nome_loja} ({tipo})"
        btns.append([KeyboardButton(text=label)])
        map_orcs[label] = o["id"]
    btns.append([KeyboardButton(text="⬅️ Voltar")])
    kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)
    await state.set_state(OrcState.historico)
    await state.update_data(historico_map=map_orcs)
    await message.answer("Selecione um orçamento para ver o extrato:", reply_markup=kb)


@router.message(OrcState.historico)
async def orc_historico_selecionar(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Voltar":
        await state.set_state(OrcState.menu)
        return await message.answer("📊 Menu de Orçamentos:", reply_markup=kb_orcamentos_menu())
    data = await state.get_data()
    map_orcs = data.get("historico_map", {})
    chave = message.text.strip()
    orc_id = map_orcs.get(chave)
    if not orc_id:
        return await message.answer("Selecione um orçamento válido.")
    itens = await listar_itens_orcamento(orc_id)
    orc_row = None
    conn = await database.get_conn()
    try:
        orc_row = await conn.fetchrow("SELECT * FROM orcamentos WHERE id = $1", orc_id)
    finally:
        await conn.close()
    texto = f"🧾 Orçamento: {orc_row.get('nome_loja') or orc_row.get('nome') or '—'} — {orc_row.get('tipo_loja') or '—'}\n"
    if orc_row.get("descricao"):
        texto += f"📄 {orc_row['descricao']}\n"
    if orc_row.get("link"):
        texto += f"🔗 {orc_row['link']}\n"
    texto += f"\n📦 Itens ({len(itens)}):\n"
    total = 0.0
    for it in itens:
        q = it.get("quantidade") or 0
        v = it.get("valor_unitario") or 0
        sub = float(q) * float(v)
        total += sub
        texto += f"• {it['item_nome']}: {q} x R${float(v):.2f} = R${sub:.2f}\n"
    texto += f"\n💰 Total estimado: R${total:.2f}"
    btns = [[KeyboardButton(text="⬅️ Voltar")], [KeyboardButton(text="⬅️ Menu Principal")]]
    kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)
    await state.set_state(OrcState.historico_detalhe)
    return await message.answer(texto, reply_markup=kb)


@router.message(OrcState.historico_detalhe)
async def orc_historico_detalhe_nav(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Voltar":
        return await orc_historico_inicio(message, state)
    if message.text == "⬅️ Menu Principal":
        await state.clear()
        return await message.answer("Voltando ao menu principal.", reply_markup=ReplyKeyboardRemove())
    return await message.answer("Use os botões para navegar.")


# exporta router (main.py já faz include_router)
router  # variável exportada