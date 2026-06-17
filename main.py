# main.py
import asyncio
import os
import re
import time
import traceback
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from dotenv import load_dotenv

import catalogo
import database

load_dotenv()
bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()

print(f"[STARTUP] main.py loaded PID={os.getpid()} ts={time.time():.3f}")


class MainState(StatesGroup):
    escolhendo_departamento = State()
    menu_principal = State()
    carrinho_menu = State()
    finalizando_mercado = State()
    historico_menu = State()
    historico_detalhe = State()
    # novos estados para remoção de item (agora em 3 passos)
    remover_escolher_categoria = State()
    remover_escolher_subcategoria = State()
    remover_informar_idx = State()


# --- HELPERS ---
async def get_dep_data(state: FSMContext):
    """
    Retorna tupla: (departamento_id, departamento_nome, departamento_emoji, catalogo_json)
    """
    data = await state.get_data()
    return (
        data.get("departamento_id"),
        data.get("departamento_nome"),
        data.get("departamento_emoji"),
        data.get("catalogo_json"),
    )


async def limpar_estado_preservando_departamento(state: FSMContext):
    data = await state.get_data()
    preserved = {
        k: data.get(k)
        for k in ("departamento_id", "departamento_nome", "departamento_emoji", "catalogo_json")
        if data.get(k) is not None
    }
    await state.clear()
    if preserved:
        await state.set_data(preserved)


def parse_decimal(text: str) -> float:
    """
    Converte strings como:
      "5,50", "5.50", "R$ 5,50", "1.234,56", "1,234.56", "  10 "
    em float. Lança ValueError se não conseguir.
    """
    if not isinstance(text, str):
        raise ValueError("valor não é string")

    s = text.strip()
    # remove símbolos de moeda e caracteres não numéricos exceto . , -
    s = re.sub(r"[^\d,.\-]", "", s)

    if s == "" or s in (".", ",", "-", "-.", "-,"):
        raise ValueError("string vazia depois de limpar")

    # casos com ambos '.' e ',' -> assumir '.' como miles e ',' como decimal (ex: 1.234,56)
    if s.count(".") > 0 and s.count(",") > 0:
        s = s.replace(".", "").replace(",", ".")
    # caso com apenas ',' -> substituir por '.'
    elif s.count(",") > 0 and s.count(".") == 0:
        s = s.replace(",", ".")
    # caso com apenas '.' -> manter (ex: 1234.56)

    # agora tentar converter
    return float(s)


# --- NEW HELPER: envia textos longos em pedaços seguros para o Telegram ---
async def send_text_in_chunks(message: types.Message, text: str, *,
                    reply_markup: types.ReplyKeyboardMarkup | None = None,
                    parse_mode: str | None = None,
                    chunk_size: int = 4000):
    """
    Divide `text` em partes <= chunk_size respeitando quebras de linha quando possível.
    Anexa `reply_markup` somente ao último chunk (para evitar keyboards duplicados).
    """
    if text is None:
        return
    if not text:
        return await message.answer("", reply_markup=reply_markup)

    # preserva quebras de linha ao dividir
    lines = text.splitlines(keepends=True)
    chunks = []
    cur = ""
    for line in lines:
        if len(cur) + len(line) > chunk_size:
            if cur:
                chunks.append(cur)
                cur = line
            else:
                # linha individual maior que chunk_size -> dividir forçado
                for i in range(0, len(line), chunk_size):
                    chunks.append(line[i:i+chunk_size])
                cur = ""
        else:
            cur += line
    if cur:
        chunks.append(cur)

    # enviar cada chunk; somente o último com reply_markup/parse_mode
    for idx, ch in enumerate(chunks):
        is_last = idx == (len(chunks) - 1)
        markup = reply_markup if is_last else None
        pmode = parse_mode if is_last else None
        await message.answer(ch, parse_mode=pmode, reply_markup=markup)


# --- KEYBOARDS ---
def kb_departamentos(departamentos):
    btns = []
    for dep in departamentos:
        texto = f"{dep['emoji']} {dep['nome']}" if dep.get("emoji") else dep["nome"]
        btns.append([KeyboardButton(text=texto)])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)


def kb_menu_principal():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛒 Compras"), KeyboardButton(text="📲 Cadastros")],
            [KeyboardButton(text="📜 Histórico"), KeyboardButton(text="📊 Orçamentos")],
            [KeyboardButton(text="🔄 Trocar Departamento")],
        ],
        resize_keyboard=True,
    )


def kb_menu_compras():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛒 Compra Avulsa"), KeyboardButton(text="📋 Minhas Listas")],
            [KeyboardButton(text="📦 Ver Carrinho")],
            [KeyboardButton(text="⬅️ Menu Principal")],
        ],
        resize_keyboard=True,
    )


def kb_menu_cadastros():
    # Conforme fluxograma: cadastros só expõe "📋 Listas"
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Listas")],
            [KeyboardButton(text="⬅️ Menu Principal")],
        ],
        resize_keyboard=True,
    )


def kb_menu_compras_minimal():
    # fallback usado em retornos simples
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⬅️ Menu Principal")]],
        resize_keyboard=True,
    )


def kb_carrinho_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🗑️ Remover Item"), KeyboardButton(text="🧹 Limpar Carrinho")],
            [KeyboardButton(text="🏁 Finalizar Compra")],
            [KeyboardButton(text="⬅️ Voltar Compras")],
        ],
        resize_keyboard=True,
    )


def kb_confirmar():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="✅ Confirmar"), KeyboardButton(text="❌ Cancelar")]],
        resize_keyboard=True,
    )


def kb_opcoes(lista, voltar=True, cancelar=False):
    """
    Gera teclado de opções do catálogo.
    - voltar: inclui botão "⬅️ Voltar" se True
    - cancelar: inclui botão "❌ Cancelar" se True (por padrão False)
    """
    btns = [[KeyboardButton(text=catalogo.formatar(opt))] for opt in lista]
    if voltar:
        btns.append([KeyboardButton(text="⬅️ Voltar")])
    if cancelar:
        btns.append([KeyboardButton(text="❌ Cancelar")])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)


# --- CATALOG HELPERS PARA MONTAR EXTRATO ---
def _buscar_produto_recursivo(no, produto, path):
    # no: node do catálogo, produto: nome exato no catálogo, path: lista com chaves encontradas
    if isinstance(no, dict):
        # se este nó tem lista de produtos
        produtos = no.get("produtos")
        if isinstance(produtos, list) and produto in produtos:
            return path
        # procurar em subcategorias e grupos
        for chave in ("subcategorias", "grupos"):
            sub = no.get(chave)
            if isinstance(sub, dict):
                for sk, sn in sub.items():
                    res = _buscar_produto_recursivo(sn, produto, path + [sk])
                    if res:
                        return res
        # procurar por filhos dict diretamente (arquiteturas variadas)
        for k, v in no.items():
            if k in ("produtos", "subcategorias", "grupos"):
                continue
            if isinstance(v, dict):
                res = _buscar_produto_recursivo(v, produto, path + [k])
                if res:
                    return res
    elif isinstance(no, list):
        if produto in no:
            return path
    return None


def encontrar_caminho_produto(produto):
    # percorre categorias de topo em busca do produto; retorna lista de chaves do caminho (ex: ['Bebidas', 'Refrigerantes'])
    for cat_key, cat_node in catalogo.CATALOGO.items():
        res = _buscar_produto_recursivo(cat_node, produto, [cat_key])
        if res:
            return res
    return None


def montar_extrato_carrinho(itens):
    """
    itens: lista de rows/dicts com campos: item_nome, quantidade, valor_unitario
    Retorna string formatada conforme solicitado, com numeração global 3 dígitos (001, 002, ...)
    """
    # agrupar: groups[cat][sub] = [itens]
    groups = {}
    total_cart = 0.0

    for r in itens:
        # suportar dict-like e asyncpg.Record / rows
        try:
            nome = r["item_nome"]
            qtd = float(r["quantidade"])
            valor_unit = float(r["valor_unitario"])
        except Exception:
            # tentativa alternativa por índice
            try:
                nome = r[1]
                qtd = float(r[2])
                valor_unit = float(r[3])
            except Exception:
                # pular item inconsistente
                continue

        total = qtd * valor_unit
        total_cart += total

        caminho = encontrar_caminho_produto(nome)
        if caminho:
            categoria = caminho[0]
            subcategoria = caminho[1] if len(caminho) > 1 else None
        else:
            categoria = "Outros"
            subcategoria = None

        groups.setdefault(categoria, {}).setdefault(subcategoria or "_no_sub", []).append({
            "nome": nome,
            "qtd": qtd,
            "valor_unit": valor_unit,
            "total": total
        })

    # montar texto com numeração global contínua (3 dígitos)
    lines = []
    lines.append("*" * 51)
    global_idx = 1
    for cat, subdict in groups.items():
        # subtotal da categoria
        cat_subtotal = sum(it["total"] for items in subdict.values() for it in items)
        lines.append(f"{cat.upper()}: R${cat_subtotal:.2f}")
        for sub, items in subdict.items():
            sub_label = "Geral" if sub == "_no_sub" else sub.title()
            sub_subtotal = sum(it["total"] for it in items)
            lines.append(f"{sub_label}: R${sub_subtotal:.2f}")
            for it in items:
                idx_label = f"{global_idx:03d}"
                lines.append(f"{idx_label}. ➥ {catalogo.formatar(it['nome'])}: {it['qtd']:.3f} x R${it['valor_unit']:.2f} = R${it['total']:.2f}")
                global_idx += 1
            lines.append("")  # linha em branco entre subcategorias
        lines.append("")  # linha em branco entre categorias
    lines.append("*" * 51)
    lines.append(f"Valor Total do Carrinho: R${total_cart:.2f}")
    return "\n".join(lines)


# --- dividir extrato por categoria e enviar por categoria ---
def dividir_extrato_por_categoria(itens):
    """
    Recebe uma lista de itens (rows/dicts com item_nome, quantidade, valor_unitario)
    Retorna (lista_de_textos_por_categoria, total_cart)
    Cada item da lista_de_textos_por_categoria contém:
      ***************************
      NOME_DA_CATEGORIA

      Subcategoria: Subtotal
      Item - qtd x valor = total
      ...
      Subtotal da categoria: R$xx.xx
    """
    groups = {}
    total_cart = 0.0

    for r in itens:
        # suportar dict-like e asyncpg.Record / rows
        try:
            nome = r["item_nome"]
            qtd = float(r["quantidade"])
            valor_unit = float(r["valor_unitario"])
        except Exception:
            try:
                nome = r[1]
                qtd = float(r[2])
                valor_unit = float(r[3])
            except Exception:
                continue

        total = qtd * valor_unit
        total_cart += total

        caminho = encontrar_caminho_produto(nome)
        if caminho:
            categoria = caminho[0]
            subcategoria = caminho[1] if len(caminho) > 1 else None
        else:
            categoria = "Outros"
            subcategoria = None

        groups.setdefault(categoria, {}).setdefault(subcategoria or "_no_sub", []).append({
            "nome": nome,
            "qtd": qtd,
            "valor_unit": valor_unit,
            "total": total
        })

    textos = []
    # opcional: ordenar categorias por nome (poderíamos ordenar por total decrescente se preferir)
    for cat in sorted(groups.keys()):
        subdict = groups[cat]
        lines = []
        lines.append(f"{cat.upper()}")
        lines.append("")  # linha em branco

        # subtotal da categoria
        cat_subtotal = sum(it["total"] for items in subdict.values() for it in items)

        for sub, items in subdict.items():
            sub_label = "Geral" if sub == "_no_sub" else sub.title()
            sub_subtotal = sum(it["total"] for it in items)
            lines.append(f"{sub_label.upper()}")
            for idx, it in enumerate(items, start=1):
                lines.append(f"{idx:03d}   {catalogo.formatar(it['nome'])}\n        {it['qtd']:.3f} x R$ {it['valor_unit']:.2f} = R$ {it['total']:.2f}")
            lines.append(f"➥ Total da subcategoria: R$ {sub_subtotal:.2f}")
            lines.append("")  # linha em branco entre subcategorias

        lines.append(f"🧮 Total da categoria: R$ {cat_subtotal:.2f}")
        textos.append("\n".join(lines).replace("_", " "))

    return textos, total_cart

async def send_extrato_por_categoria(message: types.Message, itens, *,
                                     reply_markup: types.ReplyKeyboardMarkup | None = None,
                                     parse_mode: str | None = None):
    """
    Envia cada categoria como mensagem separada (usando send_text_in_chunks para
    segurança contra mensagens muito longas). No final envia o total geral
    e anexa o reply_markup somente à última mensagem.
    """
    textos_por_cat, total = dividir_extrato_por_categoria(itens)

    if not textos_por_cat:
        # fallback: nada agrupado (ex: itens vazios)
        await send_text_in_chunks(message, "Carrinho vazio.")
        if reply_markup:
            await message.answer("", reply_markup=reply_markup)
        return

    # enviar cada categoria (sem teclado)
    for t in textos_por_cat:
        await send_text_in_chunks(message, t)

    # enviar total geral com teclado (se dado)
    total_text = ("*" * 27) + "\n" + f"Valor Total do Carrinho: R${total:.2f}"
    await send_text_in_chunks(message, total_text, reply_markup=reply_markup, parse_mode=parse_mode)


# --- Helpers para remoção: mapa global e grupos ---
def _build_global_index_map_and_groups(itens):
    """
    itens: lista (rows/dicts) retornada por database.pegar_carrinho(...)
    Retorna:
      - global_map: dict {idx_int: {'pos': original_pos, 'cat':cat, 'sub':sub, 'item': {'nome','qtd','valor_unit','total'}}}
      - groups: dict {cat: {sub: [ (pos,item_dict), ... ] } }
    A numeração segue ordem por categoria (ordenada por nome) e pela ordem dos itens dentro da lista do DB.
    """
    groups = {}
    total_cart = 0.0

    for pos, r in enumerate(itens):
        try:
            nome = r["item_nome"]
            qtd = float(r["quantidade"])
            valor_unit = float(r["valor_unitario"])
        except Exception:
            try:
                nome = r[1]
                qtd = float(r[2])
                valor_unit = float(r[3])
            except Exception:
                continue

        total = qtd * valor_unit
        total_cart += total

        caminho = encontrar_caminho_produto(nome)
        if caminho:
            categoria = caminho[0]
            subcategoria = caminho[1] if len(caminho) > 1 else None
        else:
            categoria = "Outros"
            subcategoria = None

        groups.setdefault(categoria, {}).setdefault(subcategoria or "_no_sub", []).append((
            pos,
            {"nome": nome, "qtd": qtd, "valor_unit": valor_unit, "total": total}
        ))

    # gerar mapa global_idx -> pos/item
    global_map = {}
    idx = 1
    for cat in sorted(groups.keys()):
        subdict = groups[cat]
        for sub, items in subdict.items():
            for pos, item in items:
                global_map[idx] = {"pos": pos, "cat": cat, "sub": sub, "item": item}
                idx += 1

    return global_map, groups


# --- HANDLERS ---
@dp.message(CommandStart())
async def start(message: types.Message, state: FSMContext):
    print(f"[DEBUG][PID {os.getpid()}][start] ts={time.time()} user={message.from_user.id}")
    # garante que tabela/departamentos existam
    try:
        await database.init_db()
    except Exception:
        traceback.print_exc()

    deps = await database.listar_departamentos()
    if not deps:
        await message.answer("Nenhum departamento encontrado no banco.")
        return

    await state.clear()
    await state.set_state(MainState.escolhendo_departamento)
    await message.answer("🏬 Escolha o departamento:", reply_markup=kb_departamentos(deps))


@dp.message(MainState.escolhendo_departamento)
async def escolher_departamento(message: types.Message, state: FSMContext):
    print(f"[DEBUG][PID {os.getpid()}][escolher_departamento] ts={time.time()} user={message.from_user.id}")
    deps = await database.listar_departamentos()
    escolhido = None

    for dep in deps:
        texto_botao = f"{dep['emoji']} {dep['nome']}" if dep.get("emoji") else dep["nome"]
        if message.text == texto_botao or message.text == dep["nome"]:
            escolhido = dep
            break

    if not escolhido:
        return await message.answer("Escolha um departamento válido.")

    # carrega o catálogo do departamento para uso imediato
    try:
        catalogo.carregar_catalogo_dep(escolhido.get("catalogo_json"))
    except Exception:
        pass

    await state.set_data(
        {
            "departamento_id": escolhido["id"],
            "departamento_nome": escolhido["nome"],
            "departamento_emoji": escolhido.get("emoji"),
            "catalogo_json": escolhido.get("catalogo_json"),
        }
    )
    await state.set_state(MainState.menu_principal)

    await message.answer(
        f"✅ Departamento *{escolhido['nome']}* selecionado.\n\nO que deseja fazer?",
        parse_mode="Markdown",
        reply_markup=kb_menu_principal(),
    )


# ─── MENUS ────
@dp.message(F.text == "🛒 Compras")
async def abrir_compras(message: types.Message, state: FSMContext):
    print(f"[DEBUG][PID {os.getpid()}][abrir_compras] ts={time.time()} user={message.from_user.id}")
    dep_id, *_ = await get_dep_data(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento primeiro.")
    await state.set_state(MainState.menu_principal)
    await message.answer("🛒 Menu de Compras:", reply_markup=kb_menu_compras())


@dp.message(F.text == "📲 Cadastros")
async def abrir_cadastros(message: types.Message, state: FSMContext):
    print(f"[DEBUG][PID {os.getpid()}][abrir_cadastros] ts={time.time()} user={message.from_user.id}")
    dep_id, *_ = await get_dep_data(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento primeiro.")
    await state.set_state(MainState.menu_principal)
    await message.answer("📲 Menu de Cadastros:", reply_markup=kb_menu_cadastros())


@dp.message(F.text == "⬅️ Voltar Compras")
async def voltar_compras(message: types.Message, state: FSMContext):
    print(f"[DEBUG][PID {os.getpid()}][voltar_compras] ts={time.time()} user={message.from_user.id}")
    dep_id, *_ = await get_dep_data(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento primeiro.")
    await limpar_estado_preservando_departamento(state)
    await state.set_state(MainState.menu_principal)
    await message.answer("🛒 Menu de Compras:", reply_markup=kb_menu_compras())


# ─── TROCAR DEPARTAMENTO ────
@dp.message(F.text == "🔄 Trocar Departamento")
async def trocar_departamento(message: types.Message, state: FSMContext):
    print(f"[DEBUG][PID {os.getpid()}][trocar_departamento] ts={time.time()} user={message.from_user.id}")
    deps = await database.listar_departamentos()
    if not deps:
        return await message.answer("Nenhum departamento encontrado.")
    await state.clear()
    await state.set_state(MainState.escolhendo_departamento)
    await message.answer("🏬 Escolha o departamento:", reply_markup=kb_departamentos(deps))


# ─── COMPRA AVULSA (navegação por catalogo) ────
class ShopState(StatesGroup):
    navegando = State()
    quantidade = State()
    valor = State()


@dp.message(F.text == "🛒 Compra Avulsa")
async def start_buy(message: types.Message, state: FSMContext):
    print(f"[DEBUG][PID {os.getpid()}][start_buy] ts={time.time()} user={message.from_user.id}")
    dep_id, *_ = await get_dep_data(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento primeiro.")
    await state.set_state(ShopState.navegando)
    await state.update_data(caminho=[])
    opts = list(catalogo.CATALOGO.keys())
    # mostrar botão "⬅️ Voltar" (voltar para Menu de Compras) e sem "❌ Cancelar" por padrão
    await message.answer("Escolha a categoria:", reply_markup=kb_opcoes(opts, True, False))


@dp.message(ShopState.navegando)
async def navegar(message: types.Message, state: FSMContext):
    print(f"[DEBUG][PID {os.getpid()}][navegar] ts={time.time()} user={message.from_user.id} text={message.text}")
    data = await state.get_data()
    caminho = data.get("caminho", [])

    if message.text == "⬅️ Voltar":
        if not caminho:
            # voltar para Menu de Compras (preservando departamento)
            await state.set_state(MainState.menu_principal)
            return await message.answer("🛒 Menu de Compras:", reply_markup=kb_menu_compras())
        caminho.pop()
        await state.update_data(caminho=caminho)
        opts = list(catalogo.CATALOGO.keys()) if not caminho else catalogo.obter_opcoes(caminho)
        return await message.answer("Voltando...", reply_markup=kb_opcoes(opts, True, False))

    escolha = message.text.strip()
    # tenta identificar se é categoria ou produto
    tipo, chave = catalogo.identificar_escolha(caminho, escolha)
    if tipo == "categoria":
        # avançar caminho
        chave_slug = chave
        # normaliza e avança
        caminho.append(chave_slug)
        await state.update_data(caminho=caminho)
        opts = catalogo.obter_opcoes(caminho)
        await message.answer("Selecione:", reply_markup=kb_opcoes(opts, True, False))
        return

    if tipo == "produto":
        # produto selecionado -> pedir qtd
        await state.update_data(produto=chave)
        await state.set_state(ShopState.quantidade)
        await message.answer(f"Quanto de {catalogo.formatar(chave)}?", reply_markup=ReplyKeyboardRemove())
        return

    await message.answer("Escolha inválida.")


@dp.message(ShopState.quantidade)
async def set_qtd(message: types.Message, state: FSMContext):
    try:
        qtd = parse_decimal(message.text)
        await state.update_data(qtd=qtd)
        await state.set_state(ShopState.valor)
        await message.answer("Qual o valor unitário? (Ex: 5.50)")
    except Exception:
        await message.answer("Por favor, digite um número válido para a quantidade. Exemplos: 1, 2, 1.5, 1.234,56")


@dp.message(ShopState.valor)
async def set_valor(message: types.Message, state: FSMContext):
    print(f"[DEBUG][PID {os.getpid()}][set_valor] ts={time.time()} user={message.from_user.id} text={message.text}")
    try:
        # tenta parsear o valor de forma tolerante
        valor = parse_decimal(message.text)
    except Exception:
        return await message.answer(
            "Valor inválido. Digite apenas o número do valor unitário.\n"
            "Exemplos válidos: `5.50`, `5,50`, `R$ 5,50`, `1.234,56`",
            parse_mode="Markdown"
        )

    data = await state.get_data()
    produto = data.get("produto")
    qtd = data.get("qtd")

    if produto is None or qtd is None:
        # algo no estado foi perdido — orientar usuário a recomeçar a compra
        await state.clear()
        await state.set_state(MainState.menu_principal)
        return await message.answer(
            "Ocorreu um problema (produto/quantidade não encontrados). "
            "Por favor, inicie novamente: envie /start e escolha o departamento."
        )

    dep_id, *_ = await get_dep_data(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento primeiro.")

    # Debug: log antes de chamar DB
    print(f"[DEBUG] adicionar_ao_carrinho: user={message.from_user.id} dep={dep_id} produto={produto} qtd={qtd} valor={valor}")

    # chamar a função do DB com assinatura correta (user_id, dep_id, nome, qtd, valor)
    try:
        await database.adicionar_ao_carrinho(message.from_user.id, dep_id, produto, qtd, valor)
    except Exception:
        traceback.print_exc()
        await message.answer("Erro ao salvar no carrinho. Tente novamente.")
        return

    # Recupera o carrinho do usuário no departamento
    try:
        itens = await database.pegar_carrinho(message.from_user.id, dep_id)
    except Exception:
        traceback.print_exc()
        await message.answer("Erro ao recuperar o carrinho. Tente novamente.")
        return

    # Monta e envia o extrato agrupado por categoria (cada categoria -> mensagem)
    await state.set_state(ShopState.navegando)
    await state.update_data(caminho=[])
    opts = list(catalogo.CATALOGO.keys())

    await send_extrato_por_categoria(message, itens)
    # sem botão Cancelar aqui por padrão
    return await message.answer("Deseja adicionar mais itens?", reply_markup=kb_opcoes(opts, True, False))


# ─── VER CARRINHO ────
@dp.message(F.text == "📦 Ver Carrinho")
async def ver_carrinho(message: types.Message, state: FSMContext):
    print(f"[DEBUG][PID {os.getpid()}][ver_carrinho] ts={time.time()} user={message.from_user.id}")
    dep_id, _, _, _ = await get_dep_data(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento primeiro.")
    # buscar carrinho do usuário no departamento
    try:
        itens = await database.pegar_carrinho(message.from_user.id, dep_id)
    except Exception:
        traceback.print_exc()
        return await message.answer("Erro ao recuperar o carrinho. Tente novamente.")

    if not itens:
        return await message.answer("Carrinho vazio!", reply_markup=kb_menu_compras())
    await state.set_state(MainState.carrinho_menu)
    # envia por categoria e anexa o teclado à última mensagem (total)
    await send_extrato_por_categoria(message, itens, reply_markup=kb_carrinho_menu())


# ─── INICIAR REMOÇÃO: mostra apenas CATEGORIAS presentes no carrinho
@dp.message(MainState.carrinho_menu, F.text == "🗑️ Remover Item")
async def iniciar_remover_item(message: types.Message, state: FSMContext):
    dep_id, *_ = await get_dep_data(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento primeiro.")

    try:
        itens = await database.pegar_carrinho(message.from_user.id, dep_id)
    except Exception:
        traceback.print_exc()
        return await message.answer("Erro ao recuperar o carrinho. Tente novamente.")

    if not itens:
        return await message.answer("Carrinho vazio!", reply_markup=kb_menu_compras())

    global_map, groups = _build_global_index_map_and_groups(itens)

    # construir teclado com apenas categorias (cada categoria aparece uma vez)
    btns = []
    category_map = {}  # categoria -> list(subs)
    for cat in sorted(groups.keys()):
        btns.append([KeyboardButton(text=cat.upper().replace("_", " "))])
        # obter subkeys e mapear
        subs = []
        for sub in groups[cat].keys():
            subs.append(sub)
        category_map[cat] = subs

    # adicionar botão de voltar
    btns.append([KeyboardButton(text="⬅️ Voltar")])
    kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

    # salvar mapa de categorias e o global_map no estado (será usado nos próximos passos)
    # armazenamos global_map (chaves int -> info) e category_map
    await state.update_data(remover_global_map={k: v for k, v in global_map.items()}, remover_category_map=category_map)
    await state.set_state(MainState.remover_escolher_categoria)
    await message.answer("Selecione a CATEGORIA do item que deseja remover:", reply_markup=kb)


# ─── USUÁRIO ESCOLHE CATEGORIA: mostrar lista de SUBCATEGORIAS para essa categoria
@dp.message(MainState.remover_escolher_categoria)
async def remover_escolher_categoria_handler(message: types.Message, state: FSMContext):
    text = message.text
    if text == "⬅️ Voltar":
        # voltar ao menu do carrinho
        await state.set_state(MainState.carrinho_menu)
        return await message.answer("🛒 Menu do Carrinho:", reply_markup=kb_carrinho_menu())

    data = await state.get_data()
    category_map = data.get("remover_category_map", {})
    global_map = data.get("remover_global_map", {})

    if text not in category_map:
        return await message.answer("Escolha inválida. Selecione uma das CATEGORIAS mostradas.")

    cat = text
    subs = category_map.get(cat, [])

    # montar teclado com subcategorias (exibir "Geral" quando sub == "_no_sub")
    btns = []
    for sub in subs:
        sub_label = "Geral" if sub == "_no_sub" or sub is None else (sub.title().upper() if sub != "_no_sub" else "Geral")
        # fix cases where sub might be None
        if sub is None:
            sub_label = "Geral"
        elif sub == "_no_sub":
            sub_label = "Geral"
        else:
            sub_label = sub.title()
        btns.append([KeyboardButton(text=sub_label)])
    # adicionar opção para todos (caso queira ver todos os itens da categoria)
    btns.append([KeyboardButton(text="Todos")])
    btns.append([KeyboardButton(text="⬅️ Voltar")])
    kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

    # salvar a categoria escolhida (e o global_map) no estado
    await state.update_data(remover_chosen_categoria=cat)
    await state.set_state(MainState.remover_escolher_subcategoria)
    await message.answer(f"Categoria selecionada: *{cat}*\nAgora escolha a SUBCATEGORIA:", parse_mode="Markdown", reply_markup=kb)


# ─── USUÁRIO ESCOLHE SUBCATEGORIA: mostrar itens com numeração apenas dessa subcategoria (ou todos)
@dp.message(MainState.remover_escolher_subcategoria)
async def remover_escolher_subcategoria_handler(message: types.Message, state: FSMContext):
    text = message.text
    if text == "⬅️ Voltar":
        # voltar para escolher categoria novamente
        data = await state.get_data()
        category_map = data.get("remover_category_map", {})
        btns = [[KeyboardButton(text=c)] for c in category_map.keys()]
        btns.append([KeyboardButton(text="⬅️ Voltar")])
        kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)
        await state.set_state(MainState.remover_escolher_categoria)
        return await message.answer("Selecione a CATEGORIA:", reply_markup=kb)

    data = await state.get_data()
    cat = data.get("remover_chosen_categoria")
    global_map = data.get("remover_global_map", {})

    if not cat:
        # algo deu errado, voltar ao menu do carrinho
        await state.set_state(MainState.carrinho_menu)
        return await message.answer("Ocorreu um erro. Por favor, abra o carrinho novamente.", reply_markup=kb_carrinho_menu())

    # interpretar "Todos" ou subcategoria label
    chosen_sub = None
    if text == "Todos":
        chosen_sub = "ALL"
    else:
        # map back from displayed sub_label to stored sub key:
        # as we rendered sub_label from raw keys, try to guess:
        sub_label_input = text.strip().lower()
        # tentar encontrar sub correspondente em remover_category_map
        cat_map = data.get("remover_category_map", {})
        subs = cat_map.get(cat, [])
        matched = None
        for sub in subs:
            if sub in (None, "_no_sub") and sub_label_input in ("geral", "general", "g"):
                matched = sub
                break
            if sub and sub_label_input == (sub.lower()):
                matched = sub
                break
            if sub and sub_label_input == sub.lower().replace("_", " "):
                matched = sub
                break
            # tentar título
            if sub and sub_label_input == sub.title().lower():
                matched = sub
                break
        if matched is None:
            # tentar assumir que o usuário digitou o mesmo texto (ex: "Geral")
            if text.lower() in ("geral",):
                matched = "_no_sub"
        chosen_sub = matched

    # filtrar entradas do global_map que correspondem ao cat/sub selecionados (ou todos da categoria)
    selected_entries = []
    for idx_int, info in global_map.items():
        idx = int(idx_int) if isinstance(idx_int, str) else idx_int
        if info["cat"] != cat:
            continue
        if chosen_sub == "ALL":
            selected_entries.append((idx, info))
        else:
            # normaliza chave armazenada: nas groups usamos "_no_sub" para sem sub
            sub_key = info["sub"]
            if sub_key == chosen_sub:
                selected_entries.append((idx, info))

    if not selected_entries:
        return await message.answer("Não há itens nessa seleção (o carrinho pode ter mudado). Volte e tente novamente.", reply_markup=kb_carrinho_menu())

    # montar texto com itens desta (sub)categoria (usando idx formatado com 3 dígitos)
    lines = []
    sub_label_print = "Todos" if chosen_sub == "ALL" else ("Geral" if chosen_sub in ("_no_sub", None) else chosen_sub.title())
    lines.append(f"Itens em: {cat} / {sub_label_print}")
    lines.append("")
    for idx, info in selected_entries:
        it = info["item"]
        idx_label = f"{idx:03d}"
        lines.append(f"{idx_label}. {catalogo.formatar(it['nome'])} - {it['qtd']:.3f} x R${it['valor_unit']:.2f} = R${it['total']:.2f}")

    lines.append("")
    lines.append("Envie o número do item para remover (ex: 003) ou '⬅️ Voltar' para retornar.")
    texto = "\n".join(lines)

    # salvar o mapa reduzido para validação posterior (idx -> item detalhes)
    remover_map_sel = {idx: info for idx, info in selected_entries}
    await state.update_data(remover_choice_map={k: v for k, v in remover_map_sel.items()}, remover_chosen_subcategoria=chosen_sub)
    await state.set_state(MainState.remover_informar_idx)
    # remover teclado (usuário digitará o número)
    await message.answer(texto, reply_markup=ReplyKeyboardRemove())


# ─── USUÁRIO INFORMA O IDX A REMOVER
@dp.message(MainState.remover_informar_idx)
async def remover_informar_idx_handler(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if text == "⬅️ Voltar":
        # voltar para escolher subcategoria (reusar handler)
        data = await state.get_data()
        cat = data.get("remover_chosen_categoria")
        # reconstruir teclado de subcategorias
        cat_map = data.get("remover_category_map", {})
        subs = cat_map.get(cat, [])
        btns = []
        for sub in subs:
            if sub is None or sub == "_no_sub":
                sub_label = "Geral"
            else:
                sub_label = sub.title()
            btns.append([KeyboardButton(text=sub_label)])
        btns.append([KeyboardButton(text="Todos")])
        btns.append([KeyboardButton(text="⬅️ Voltar")])
        kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)
        await state.set_state(MainState.remover_escolher_subcategoria)
        return await message.answer("Escolha a SUBCATEGORIA:", reply_markup=kb)

    # aceitar formatos como "003" ou "3"
    try:
        idx_int = int(text)
    except Exception:
        # tentar remover zeros à esquerda
        try:
            idx_int = int(text.lstrip("0") or "0")
        except Exception:
            return await message.answer("Número inválido. Envie o número do item (ex: 003).")

    data = await state.get_data()
    remover_choice_map = data.get("remover_choice_map", {})
    # validar se idx está disponível no mapa atual
    if idx_int not in remover_choice_map:
        return await message.answer("Número não encontrado entre os itens mostrados. Verifique e tente novamente ou envie '⬅️ Voltar'.")

    target_info = remover_choice_map[idx_int]
    target_item = target_info["item"]  # {nome, qtd, valor_unit, total}

    dep_id, *_ = await get_dep_data(state)
    try:
        itens = await database.pegar_carrinho(message.from_user.id, dep_id)
    except Exception:
        traceback.print_exc()
        return await message.answer("Erro ao recuperar o carrinho. Tente novamente.")

    # localizar a primeira ocorrência que bate com nome, quantidade e valor_unit
    found_pos = None
    for pos, r in enumerate(itens):
        try:
            nome = r["item_nome"]
            qtd = float(r["quantidade"])
            valor_unit = float(r["valor_unitario"])
        except Exception:
            try:
                nome = r[1]
                qtd = float(r[2])
                valor_unit = float(r[3])
            except Exception:
                continue

        # comparar com tolerância em floats
        if nome == target_item["nome"] and abs(qtd - float(target_item["qtd"])) < 1e-9 and abs(valor_unit - float(target_item["valor_unit"])) < 1e-9:
            found_pos = pos
            break

    if found_pos is None:
        # talvez o carrinho mudou; informar e pedir para recomeçar
        await state.set_state(MainState.carrinho_menu)
        return await message.answer("Não foi possível localizar o item no carrinho (o carrinho pode ter mudado). Por favor, abra o carrinho novamente.", reply_markup=kb_carrinho_menu())

    # construir nova lista sem o item encontrado
    nova_lista = []
    for pos, r in enumerate(itens):
        if pos == found_pos:
            continue
        # explicitar os campos ao re-adicionar
        try:
            nome = r["item_nome"]
            qtd = float(r["quantidade"])
            valor_unit = float(r["valor_unitario"])
        except Exception:
            # fallback por índice
            nome = r[1]
            qtd = float(r[2])
            valor_unit = float(r[3])
        nova_lista.append((nome, qtd, valor_unit))

    # regravar o carrinho: limpar e re-adicionar
    try:
        await database.limpar_carrinho(message.from_user.id, dep_id)
        for nome, qtd, valor_unit in nova_lista:
            await database.adicionar_ao_carrinho(message.from_user.id, dep_id, nome, qtd, valor_unit)
    except Exception:
        traceback.print_exc()
        return await message.answer("Erro ao atualizar o carrinho. Tente novamente mais tarde.")

    await state.set_state(MainState.carrinho_menu)
    # confirmar e enviar extrato atualizado
    await message.answer(f"Item {idx_int:03d} removido com sucesso.", reply_markup=kb_carrinho_menu())
    try:
        itens_atual = await database.pegar_carrinho(message.from_user.id, dep_id)
        await send_extrato_por_categoria(message, itens_atual, reply_markup=kb_carrinho_menu())
    except Exception:
        traceback.print_exc()
        # em caso de falha ao mostrar extrato, apenas confirmar
        await message.answer("Carrinho atualizado, mas não foi possível exibir o extrato no momento.")


# ─── LIMPAR CARRINHO e CONFIRMAR AÇÕES ────
@dp.message(MainState.carrinho_menu, F.text == "🧹 Limpar Carrinho")
async def limpar_carrinho_menu(message: types.Message, state: FSMContext):
    await state.update_data(acao_pendente="limpar")
    await message.answer("⚠️ Tem certeza que deseja limpar todo o carrinho?", reply_markup=kb_confirmar())


@dp.message(MainState.carrinho_menu, F.text == "✅ Confirmar")
async def confirmar_acao_carrinho(message: types.Message, state: FSMContext):
    dep_id, *_ = await get_dep_data(state)
    data = await state.get_data()
    acao = data.get("acao_pendente")

    if acao == "limpar":
        # limpar apenas o carrinho do usuário no departamento
        try:
            await database.limpar_carrinho(message.from_user.id, dep_id)
        except Exception:
            traceback.print_exc()
            # mensagem amigável
            await message.answer("Erro ao limpar o carrinho. Tente novamente.")
            return

        await limpar_estado_preservando_departamento(state)
        await state.set_state(MainState.menu_principal)
        await message.answer("🧹 Carrinho limpo!", reply_markup=kb_menu_compras())

    elif acao == "finalizar":
        mercado = data.get("mercado_pendente", "Não informado")
        itens_detalhe = data.get("itens_detalhe", [])
        total = data.get("total", 0)

        try:
            await database.salvar_historico(dep_id, data.get("lista_nome", "Compra Avulsa"), mercado, itens_detalhe, total)
            # limpar apenas carrinho do usuário no departamento
            await database.limpar_carrinho(message.from_user.id, dep_id)
        except Exception:
            traceback.print_exc()
            await message.answer("Erro ao salvar histórico. Tente novamente.")
            return

        await limpar_estado_preservando_departamento(state)
        await state.set_state(MainState.menu_principal)

        await message.answer(
            f"✅ Compra finalizada no *{mercado}*!\n💰 Total: R${total:.2f}\n📦 {len(itens_detalhe)} itens registrados no histórico.",
            parse_mode="Markdown",
            reply_markup=kb_menu_principal(),
        )


@dp.message(MainState.carrinho_menu, F.text == "❌ Cancelar")
async def cancelar_acao_carrinho(message: types.Message, state: FSMContext):
    dep_id, *_ = await get_dep_data(state)
    # pegar carrinho do usuário no departamento
    try:
        itens = await database.pegar_carrinho(message.from_user.id, dep_id)
    except Exception:
        traceback.print_exc()
        return await message.answer("Erro ao recuperar o carrinho. Tente novamente.")

    if not itens:
        return await message.answer("Carrinho vazio!", reply_markup=kb_menu_compras())
    # enviar por categoria e anexa o teclado à última mensagem (total)
    await send_extrato_por_categoria(message, itens, reply_markup=kb_carrinho_menu())


# ─── FINALIZAR COMPRA (via carrinho) ────
@dp.message(MainState.carrinho_menu, F.text == "🏁 Finalizar Compra")
async def finalizar_do_carrinho(message: types.Message, state: FSMContext):
    print(f"[DEBUG][PID {os.getpid()}][finalizar_do_carrinho] ts={time.time()} user={message.from_user.id}")
    dep_id, *_ = await get_dep_data(state)
    try:
        itens = await database.pegar_carrinho(message.from_user.id, dep_id)
    except Exception:
        traceback.print_exc()
        return await message.answer("Erro ao recuperar o carrinho. Tente novamente.")

    if not itens:
        return await message.answer("Carrinho vazio!", reply_markup=kb_menu_compras())

    texto = "🛒 *Resumo do carrinho:*\n\n"
    total = 0
    itens_detalhe = []
    # numeração global no resumo também
    for idx, item in enumerate(itens, start=1):
        # suportar dict/row
        try:
            nome = item["item_nome"]
            qtd = item["quantidade"]
            valor_unit = item["valor_unitario"]
        except Exception:
            nome = item[1]
            qtd = item[2]
            valor_unit = item[3]
        sub = float(qtd) * float(valor_unit)
        total += sub
        idx_label = f"{idx:03d}"
        texto += f"{idx_label}. {catalogo.formatar(nome)}: {qtd}x R${float(valor_unit):.2f} = R${sub:.2f}\n"
        itens_detalhe.append({"nome": nome, "quantidade": qtd, "valor_unitario": valor_unit})

    texto += f"\n💰 *Total: R${total:.2f}*\n\n🏪 Qual o nome do mercado?"
    await state.set_state(MainState.finalizando_mercado)
    await state.update_data(itens_detalhe=itens_detalhe, total=total)
    # usar envio em chunks (parse_mode Markdown)
    await send_text_in_chunks(message, texto, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())


@dp.message(MainState.finalizando_mercado)
async def finalizar_mercado(message: types.Message, state: FSMContext):
    print(f"[DEBUG][PID {os.getpid()}][finalizar_mercado] ts={time.time()} user={message.from_user.id} text={message.text}")
    dep_id, dep_nome, _, _ = await get_dep_data(state)
    if not dep_id:
        await state.clear()
        return await message.answer("Envie /start e escolha um departamento primeiro.")
    mercado = message.text.strip()
    data = await state.get_data()
    itens_detalhe = data.get("itens_detalhe", [])
    total = data.get("total", 0)

    # Guarda mercado e pede confirmação no menu de carrinho
    await state.update_data(mercado_pendente=mercado)
    await state.set_state(MainState.carrinho_menu)
    await state.update_data(acao_pendente="finalizar")

    texto = (
        f"🏪 Mercado: *{mercado}*\n"
        f"💰 Total: *R${total:.2f}*\n"
        f"📦 {len(itens_detalhe)} itens\n\n"
        f"Confirmar finalização?"
    )
    await message.answer(texto, parse_mode="Markdown", reply_markup=kb_confirmar())


# ─── HISTÓRICO ────
@dp.message(F.text == "📜 Histórico")
async def abrir_historico(message: types.Message, state: FSMContext):
    print(f"[DEBUG][PID {os.getpid()}][abrir_historico] ts={time.time()} user={message.from_user.id}")
    dep_id, dep_nome, _, _ = await get_dep_data(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento primeiro.")

    compras = await database.listar_historico(dep_id)
    if not compras:
        return await message.answer("📜 Nenhuma compra registrada ainda.", reply_markup=kb_menu_principal())

    btns = []
    compras_list = []
    for c in compras:
        data_fmt = c["data"].strftime("%d/%m/%Y %H:%M") if c.get("data") else "?"
        label = f"🏪 {c['mercado']} — R${c['total']:.2f} ({data_fmt})"
        btns.append([KeyboardButton(text=label)])
        compras_list.append(dict(c))
    btns.append([KeyboardButton(text="⬅️ Menu Principal")])

    kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)
    await state.set_state(MainState.historico_menu)
    await state.set_data({"historico_compras": compras_list})
    await message.answer(f"📜 *Histórico de compras — {dep_nome}*\nSelecione uma compra para ver os detalhes:", parse_mode="Markdown", reply_markup=kb)


@dp.message(MainState.historico_menu)
async def selecionar_historico(message: types.Message, state: FSMContext):
    # NOTE: "⬅️ Menu Principal" é tratado pelo handler centralizado (ver abaixo).
    data = await state.get_data()
    compras = data.get("historico_compras", [])
    compra_selecionada = None
    for c in compras:
        from datetime import datetime
        if isinstance(c["data"], str):
            dt = datetime.fromisoformat(c["data"])
        else:
            dt = c["data"]
        data_fmt = dt.strftime("%d/%m/%Y %H:%M")
        label = f"🏪 {c['mercado']} — R${c['total']:.2f} ({data_fmt})"
        if message.text == label:
            compra_selecionada = c
            break

    if not compra_selecionada:
        return await message.answer("Selecione uma compra válida.")

    itens = await database.listar_itens_historico(compra_selecionada["id"])
    texto = (
        f"🏪 *Mercado:* {compra_selecionada['mercado']}\n"
        f"💰 *Total:* R${compra_selecionada['total']:.2f}\n"
        f"📅 *Data:* {data_fmt}\n\n"
        f"📦 *Itens:*\n"
    )
    for item in itens:
        sub = item["quantidade"] * item["valor_unitario"]
        texto += f"• {item['item_nome']}: {item['quantidade']:.3f}x R${item['valor_unitario']:.2f} = R${sub:.2f}\n"

    kb_voltar = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⬅️ Voltar Histórico")], [KeyboardButton(text="⬅️ Menu Principal")]],
        resize_keyboard=True,
    )
    await state.set_state(MainState.historico_detalhe)
    await send_text_in_chunks(message, texto, parse_mode="Markdown", reply_markup=kb_voltar)


@dp.message(MainState.historico_detalhe)
async def historico_detalhe_nav(message: types.Message, state: FSMContext):
    dep_id, dep_nome, _, _ = await get_dep_data(state)

    if message.text == "⬅️ Voltar Histórico":
        compras = await database.listar_historico(dep_id)
        btns = []
        for c in compras:
            data_fmt = c["data"].strftime("%d/%m/%Y %H:%M") if c.get("data") else "?"
            label = f"🏪 {c['mercado']} — R${c['total']:.2f} ({data_fmt})"
            btns.append([KeyboardButton(text=label)])
        btns.append([KeyboardButton(text="⬅️ Menu Principal")])
        kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)
        await state.set_state(MainState.historico_menu)
        await state.update_data(historico_compras=[dict(c) for c in compras])
        return await message.answer("📜 Selecione uma compra:", reply_markup=kb)

    # NOTE: "⬅️ Menu Principal" é tratado pelo handler centralizado (ver abaixo).


# Centralizado: trata "⬅️ Menu Principal" apenas nos states onde isso realmente
# deve voltar ao menu principal, evitando interceptar botões de navegação interna.
@dp.message(
    MainState.menu_principal,
    MainState.carrinho_menu,
    MainState.historico_menu,
    MainState.historico_detalhe,
    F.text == "⬅️ Menu Principal",
)
async def voltar_menu_principal(message: types.Message, state: FSMContext):
    print(f"[DEBUG][PID {os.getpid()}][voltar_menu_principal] ts={time.time()} user={message.from_user.id}")
    dep_id, *_ = await get_dep_data(state)
    if not dep_id:
        # sem departamento escolhido — reiniciar fluxo
        await state.clear()
        await state.set_state(MainState.escolhendo_departamento)
        deps = await database.listar_departamentos()
        return await message.answer("🏬 Escolha o departamento:", reply_markup=kb_departamentos(deps))

    # preservar departamento e voltar ao menu principal
    await limpar_estado_preservando_departamento(state)
    await state.set_state(MainState.menu_principal)
    await message.answer("Menu principal:", reply_markup=kb_menu_principal())


# ─── CHAMA ROTERS EXTERNOS (listas) E START ────
async def main():
    # inclui router de listas (import dentro da função para evitar ciclos)
    from listas import router as listas_router
    dp.include_router(listas_router)

    # tenta incluir router de orçamentos se o módulo existir
    try:
        from orcamentos import router as orc_router
        dp.include_router(orc_router)
    except Exception as e:
        print(f"[WARN] não foi possível incluir orcamentos router: {e}")

    print(f"[STARTUP] entering dp.start_polling PID={os.getpid()} ts={time.time()}")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Interrupted by user")
    except Exception:
        traceback.print_exc()
        # tenta fechar sessão do bot de forma graciosa
        try:
            asyncio.run(bot.session.close())
        except Exception:
            pass