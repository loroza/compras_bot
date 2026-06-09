# orcamentos.py
import traceback
from aiogram import Router, types, F
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import database  # deve expor helpers de conexão e funções como pegar_listas_disponiveis / pegar_itens_da_lista

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


# --- Keyboards helpers ---
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


# --- Utilitários ---
def parse_decimal(text: str) -> float:
    """Tolerant decimal parser."""
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


def normalize_label(s: str) -> str:
    if not s:
        return ""
    return " ".join(s.strip().split()).lower()


def build_product_label(prod):
    """
    Gera label hierárquico para produtos:
    Categoria > Subcategoria > Produto — Unidade — R$X.XX
    Aceita dicts com keys variadas ou strings.
    """
    if isinstance(prod, str):
        return prod
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
    Gera label exibido para itens do orçamento:
    ID:XX | Categoria > Subcategoria > Produto — Unidade — R$X.XX
    """
    try:
        nome = item_row.get("item_nome") or item_row.get("nome") or ""
        categoria = item_row.get("categoria") or ""
        sub = item_row.get("subcategoria") or ""
        unidade = item_row.get("unidade") or ""
        valor = item_row.get("valor_unitario") or 0.0
        id_ = item_row.get("id")
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


# --- DB helpers específicos ---
async def criar_orcamento(dep_id, tipo_loja, nome_loja, descricao, link, lista_id, criado_por, itens):
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
    try:
        await ensure_tables()
    except Exception:
        traceback.print_exc()
    await state.set_state(OrcState.menu)
    await message.answer("📊 Menu de Orçamentos:", reply_markup=kb_orcamentos_menu())


@router.message(OrcState.menu, F.text == "⬅️ Voltar")
async def orc_voltar_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Voltando...", reply_markup=ReplyKeyboardRemove())


# ── Novo orçamento ──
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
    itens = await database.pegar_itens_da_lista(lista_id)
    if not itens:
        return await message.answer("A lista selecionada não contém itens. Use outra lista ou adicione itens.", reply_markup=kb_voltar())

    existentes = { normalize_label(i.get("item_nome") if isinstance(i, dict) else str(i))
                   for i in data.get("novo_itens", []) }

    btns = []
    prod_map = {}
    prod_map_norm = {}
    for i in itens:
        label = build_product_label(i)
        norm = normalize_label(label)
        if norm in existentes:
            continue
        btns.append([KeyboardButton(text=label)])
        prod_key = i.get("id") if isinstance(i, dict) else i
        prod_map[label] = prod_key
        prod_map_norm[norm] = prod_key

    if not btns:
        return await message.answer("Todos os itens desta lista já foram adicionados ao orçamento. Use '✅ Finalizar' ou '➕ Adicionar outro item' para revisar.", reply_markup=kb_confirmar_cancelar())

    btns.append([KeyboardButton(text="⬅️ Voltar")])
    kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)
    await state.set_state(OrcState.novo_selecionar_produto)
    await state.update_data(novo_produtos_map=prod_map, novo_produtos_map_norm=prod_map_norm)
    await message.answer("Selecione um produto da lista para adicionar ao orçamento (categoria > subcategoria > produto > unidade > valor):", reply_markup=kb)


@router.message(OrcState.novo_selecionar_produto)
async def orc_novo_produto_handler(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Voltar":
        await state.set_state(OrcState.novo_selecionar_lista)
        return await orc_novo_listas_prompt(message, state)

    data = await state.get_data()
    prod_map = data.get("novo_produtos_map", {}) or {}
    prod_map_norm = data.get("novo_produtos_map_norm", {}) or {}
    chave_raw = message.text or ""
    chave = chave_raw.strip()
    norm = normalize_label(chave)

    produto_key = prod_map.get(chave)
    if produto_key is None:
        produto_key = prod_map_norm.get(norm)
    if produto_key is None:
        for lbl in prod_map.keys():
            if normalize_label(lbl).startswith(norm) or norm.startswith(normalize_label(lbl)):
                produto_key = prod_map[lbl]
                chave = lbl
                break
    if produto_key is None:
        if chave.lower().startswith("id:"):
            try:
                idnum = int(chave.split(":")[1].strip())
                for lbl, pk in prod_map.items():
                    if pk == idnum:
                        produto_key = pk
                        chave = lbl
                        break
            except Exception:
                pass

    if produto_key is None:
        produto_key = chave
        chave = chave_raw

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
    lista_itens.append({"item_nome": produto_label, "quantidade": data.get("novo_qtd", 1), "valor_unitario": valor})
    await state.update_data(novo_itens=lista_itens)
    await state.set_state(OrcState.novo_confirmar)
    texto = "Item adicionado:\n"
    texto += f"• {produto_label} — {data.get('novo_qtd', 1)} x R${valor:.2f}\n\n"
    texto += f"Itens até agora: {len(lista_itens)}\n"
    await message.answer(texto, reply_markup=kb_confirmar_cancelar())


@router.message(OrcState.novo_confirmar)
async def orc_novo_confirmar_handler(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Voltar":
        await state.set_state(OrcState.novo_selecionar_lista)
        return await orc_novo_listas_prompt(message, state)
    if message.text == "➕ Adicionar outro item":
        data = await state.get_data()
        lista_id = data.get("novo_lista_id")
        itens = await database.pegar_itens_da_lista(lista_id)
        if not itens:
            return await message.answer("Lista vazia.")
        existentes = { normalize_label(i.get("item_nome") if isinstance(i, dict) else str(i))
                       for i in data.get("novo_itens", []) }

        btns = []
        prod_map = {}
        prod_map_norm = {}
        for i in itens:
            label = build_product_label(i)
            norm = normalize_label(label)
            if norm in existentes:
                continue
            btns.append([KeyboardButton(text=label)])
            prod_key = i.get("id") if isinstance(i, dict) else i
            prod_map[label] = prod_key
            prod_map_norm[norm] = prod_key
        if not btns:
            return await message.answer("Todos os itens desta lista já foram adicionados ao orçamento.", reply_markup=kb_confirmar_cancelar())
        btns.append([KeyboardButton(text="⬅️ Voltar")])
        kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)
        await state.set_state(OrcState.novo_selecionar_produto)
        await state.update_data(novo_produtos_map=prod_map, novo_produtos_map_norm=prod_map_norm)
        return await message.answer("Selecione produto:", reply_markup=kb)

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

    return await message.answer("Use os botões para finalizar ou adicionar mais itens.", reply_markup=kb_confirmar_cancelar())


# ── Editar orçamento ──
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
    await state.update_data(editar_orc_id=orc_id)
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
        dep_id = (await state.get_data()).get("departamento_id")
        listas = await database.pegar_listas_disponiveis(dep_id)
        if not listas:
            return await message.answer("Nenhuma lista disponível para selecionar.")
        btns = []
        for l in listas:
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
    itens = await database.pegar_itens_da_lista(lista_id)
    if not itens:
        return await message.answer("Lista vazia.")
    orc_id = data.get("editar_orc_id")
    existentes_rows = await listar_itens_orcamento(orc_id) if orc_id else []
    existentes = { normalize_label(r.get("item_nome")) for r in existentes_rows }

    btns = []
    prod_map = {}
    prod_map_norm = {}
    for i in itens:
        label = build_product_label(i)
        norm = normalize_label(label)
        if norm in existentes:
            continue
        btns.append([KeyboardButton(text=label)])
        prod_key = i.get("id") if isinstance(i, dict) else i
        prod_map[label] = prod_key
        prod_map_norm[norm] = prod_key
    if not btns:
        return await message.answer("Todos os itens desta lista já constam no orçamento selecionado.", reply_markup=kb_voltar())
    btns.append([KeyboardButton(text="⬅️ Voltar")])
    kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)
    await state.update_data(editar_incluir_lista_id=lista_id, editar_incluir_produtos_map=prod_map, editar_incluir_produtos_map_norm=prod_map_norm)
    await state.set_state(OrcState.editar_incluir_produto_qtd)
    await message.answer("Selecione o produto para incluir (categoria > subcategoria > produto > unidade > valor):", reply_markup=kb)


@router.message(OrcState.editar_incluir_produto_qtd)
async def orc_editar_incluir_produto_qtd_handler(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Voltar":
        await state.set_state(OrcState.editar_menu)
        return await message.answer("Voltando ao menu de edição.")
    data = await state.get_data()
    prod_map = data.get("editar_incluir_produtos_map", {}) or {}
    prod_map_norm = data.get("editar_incluir_produtos_map_norm", {}) or {}
    chosen_raw = message.text or ""
    chosen = chosen_raw.strip()
    norm = normalize_label(chosen)

    prod_key = prod_map.get(chosen) or prod_map_norm.get(norm)
    if prod_key is None:
        for lbl in prod_map.keys():
            if normalize_label(lbl).startswith(norm) or norm.startswith(normalize_label(lbl)):
                prod_key = prod_map[lbl]
                chosen = lbl
                break
    if prod_key is None and chosen.lower().startswith("id:"):
        try:
            idnum = int(chosen.split(":")[1].strip())
            for lbl, pk in prod_map.items():
                if pk == idnum:
                    prod_key = pk
                    chosen = lbl
                    break
        except Exception:
            pass
    if prod_key is None:
        prod_key = chosen
        chosen = chosen_raw

    await state.update_data(editar_incluir_produto=chosen, editar_incluir_qtd=None)
    await state.set_state(OrcState.editar_incluir_produto_valor)
    await message.answer(f"Quantidade para {chosen}:", reply_markup=ReplyKeyboardRemove())


@router.message(OrcState.editar_incluir_produto_valor)
async def orc_editar_incluir_produto_valor_handler(message: types.Message, state: FSMContext):
    data = await state.get_data()
    # se ainda não definimos qtd, esta mensagem é a qtd
    if data.get("editar_incluir_qtd") is None:
        try:
            qtd = parse_decimal(message.text)
        except Exception:
            return await message.answer("Quantidade inválida. Digite um número válido.")
        await state.update_data(editar_incluir_qtd=qtd)
        await message.answer("Agora digite o valor unitário (ex: 5.50):")
        return

    # agora esta mensagem é o valor unitário
    try:
        valor = parse_decimal(message.text)
    except Exception:
        return await message.answer("Valor inválido. Digite novamente.")
    data = await state.get_data()
    produto_label = data.get("editar_incluir_produto")
    qtd = data.get("editar_incluir_qtd", 1)
    orc_id = data.get("editar_orc_id")
    lista_id = data.get("editar_incluir_lista_id")

    try:
        await adicionar_item_orc(orc_id, produto_label, qtd, valor)
    except Exception:
        traceback.print_exc()
        return await message.answer("Erro ao adicionar item. Tente novamente.")

    # não limpar a lista_id — vamos reabrir a seleção para adicionar mais itens da mesma lista
    # obter itens restantes da lista, excluindo os já adicionados no orçamento
    itens_da_lista = await database.pegar_itens_da_lista(lista_id) if lista_id else []
    existentes_rows = await listar_itens_orcamento(orc_id) if orc_id else []
    existentes = { normalize_label(r.get("item_nome")) for r in existentes_rows }

    btns = []
    prod_map = {}
    prod_map_norm = {}
    for i in itens_da_lista:
        label = build_product_label(i)
        norm = normalize_label(label)
        if norm in existentes:
            continue
        btns.append([KeyboardButton(text=label)])
        prod_key = i.get("id") if isinstance(i, dict) else i
        prod_map[label] = prod_key
        prod_map_norm[norm] = prod_key

    # preparar texto com itens do orçamento atualizado
    itens_atualizados = await listar_itens_orcamento(orc_id)
    texto = "Item adicionado ao orçamento.\n\nItens do orçamento (atualizado):\n"
    for it in itens_atualizados:
        texto += f"• {build_orc_item_label(it)}\n"

    if not btns:
        # se não há mais itens disponíveis nesta lista, voltar ao menu de edição
        await state.update_data(editar_incluir_produto=None, editar_incluir_qtd=None, editar_incluir_lista_id=None,
                                editar_incluir_produtos_map=None, editar_incluir_produtos_map_norm=None)
        await state.set_state(OrcState.editar_menu)
        return await message.answer(texto + "\nTodos os itens desta lista já constam no orçamento.", reply_markup=ReplyKeyboardRemove())

    # caso ainda existam itens, mostrar keyboard para selecionar próximo produto
    btns.append([KeyboardButton(text="⬅️ Voltar")])
    kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)
    await state.update_data(editar_incluir_produtos_map=prod_map, editar_incluir_produtos_map_norm=prod_map_norm,
                            editar_incluir_produto=None, editar_incluir_qtd=None)
    # voltar para o estado que recebe a seleção do produto (mesma máquina de estados usada antes)
    await state.set_state(OrcState.editar_incluir_produto_qtd)
    return await message.answer(texto + "\nSelecione o próximo produto para incluir (ou ⬅️ Voltar):", reply_markup=kb)


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
    orc_id = data.get("editar_orc_id")
    try:
        await excluir_item_orc_por_id(item_id)
    except Exception:
        traceback.print_exc()
        return await message.answer("Erro ao excluir item. Tente novamente.")
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
    orc_id = data.get("editar_orc_id")
    itens = await listar_itens_orcamento(orc_id)
    texto = "Itens do orçamento (atualizado):\n"
    for it in itens:
        texto += f"• {build_orc_item_label(it)}\n"
    await state.set_state(OrcState.editar_menu)
    return await message.answer("Item atualizado com sucesso.\n\n" + texto, reply_markup=ReplyKeyboardRemove())


# ── Histórico ──
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


# exporta router
router