import asyncio
import os
import re
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


class MainState(StatesGroup):
    escolhendo_departamento = State()
    menu_principal = State()
    carrinho_menu = State()
    finalizando_mercado = State()
    historico_menu = State()
    historico_detalhe = State()


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
            [KeyboardButton(text="📜 Histórico"), KeyboardButton(text="🔄 Trocar Departamento")],
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


def kb_opcoes(lista, voltar=True):
    btns = [[KeyboardButton(text=catalogo.formatar(opt))] for opt in lista]
    if voltar:
        btns.append([KeyboardButton(text="⬅️ Voltar")])
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
    Retorna string formatada conforme solicitado.
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

    # montar texto
    lines = []
    lines.append("*" * 51)
    for cat, subdict in groups.items():
        # subtotal da categoria
        cat_subtotal = sum(it["total"] for items in subdict.values() for it in items)
        lines.append(f"{cat.upper()}: R${cat_subtotal:.2f}")
        for sub, items in subdict.items():
            sub_label = "Geral" if sub == "_no_sub" else sub.title()
            sub_subtotal = sum(it["total"] for it in items)
            lines.append(f"{sub_label}: R${sub_subtotal:.2f}")
            for it in items:
                lines.append(f" ➥ {catalogo.formatar(it['nome'])}: {it['qtd']} x R${it['valor_unit']:.2f} = R${it['total']:.2f}")
            lines.append("")  # linha em branco entre subcategorias
        lines.append("")  # linha em branco entre categorias
    lines.append("*" * 51)
    lines.append(f"Valor Total do Carrinho: R${total_cart:.2f}")
    return "\n".join(lines)


# --- HANDLERS ---
@dp.message(CommandStart())
async def start(message: types.Message, state: FSMContext):
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
    dep_id, *_ = await get_dep_data(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento primeiro.")
    await state.set_state(MainState.menu_principal)
    await message.answer("🛒 Menu de Compras:", reply_markup=kb_menu_compras())


@dp.message(F.text == "📲 Cadastros")
async def abrir_cadastros(message: types.Message, state: FSMContext):
    dep_id, *_ = await get_dep_data(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento primeiro.")
    await state.set_state(MainState.menu_principal)
    await message.answer("📲 Menu de Cadastros:", reply_markup=kb_menu_cadastros())


@dp.message(F.text == "⬅️ Menu Principal")
async def voltar_menu_principal(message: types.Message, state: FSMContext):
    dep_id, *_ = await get_dep_data(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento primeiro.")
    await limpar_estado_preservando_departamento(state)
    await state.set_state(MainState.menu_principal)
    await message.answer("Menu principal:", reply_markup=kb_menu_principal())


@dp.message(F.text == "⬅️ Voltar Compras")
async def voltar_compras(message: types.Message, state: FSMContext):
    dep_id, *_ = await get_dep_data(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento primeiro.")
    await limpar_estado_preservando_departamento(state)
    await state.set_state(MainState.menu_principal)
    await message.answer("🛒 Menu de Compras:", reply_markup=kb_menu_compras())


# ─── TROCAR DEPARTAMENTO ────
@dp.message(F.text == "🔄 Trocar Departamento")
async def trocar_departamento(message: types.Message, state: FSMContext):
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
    dep_id, *_ = await get_dep_data(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento primeiro.")
    await state.set_state(ShopState.navegando)
    await state.update_data(caminho=[])
    opts = list(catalogo.CATALOGO.keys())
    await message.answer("Escolha a categoria:", reply_markup=kb_opcoes(opts, True))


@dp.message(ShopState.navegando)
async def navegar(message: types.Message, state: FSMContext):
    data = await state.get_data()
    caminho = data.get("caminho", [])

    if message.text == "⬅️ Voltar":
        if not caminho:
            await state.clear()
            return await message.answer("Menu Principal:", reply_markup=kb_menu_principal())
        caminho.pop()
        await state.update_data(caminho=caminho)
        opts = list(catalogo.CATALOGO.keys()) if not caminho else catalogo.obter_opcoes(caminho)
        return await message.answer("Voltando...", reply_markup=kb_opcoes(opts, len(caminho) > 0))

    if message.text == "❌ Cancelar":
        await state.clear()
        return await message.answer("Operação cancelada.", reply_markup=kb_menu_principal())

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
        await message.answer("Selecione:", reply_markup=kb_opcoes(opts))
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

    # Monta e envia o extrato
    extrato = montar_extrato_carrinho(itens)

    # NÃO limpar o estado: voltar para navegação para permitir adicionar mais itens
    await state.set_state(ShopState.navegando)
    await state.update_data(caminho=[])

    opts = list(catalogo.CATALOGO.keys())
    await message.answer(extrato)
    return await message.answer("Deseja adicionar mais itens?", reply_markup=kb_opcoes(opts, False))


# ─── VER CARRINHO ────
@dp.message(F.text == "📦 Ver Carrinho")
async def ver_carrinho(message: types.Message, state: FSMContext):
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
    texto = montar_extrato_carrinho(itens)
    await state.set_state(MainState.carrinho_menu)
    await message.answer(texto, reply_markup=kb_carrinho_menu())


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
    texto = montar_extrato_carrinho(itens)
    await message.answer(texto, reply_markup=kb_carrinho_menu())


# ─── FINALIZAR COMPRA (via carrinho) ────
@dp.message(MainState.carrinho_menu, F.text == "🏁 Finalizar Compra")
async def finalizar_do_carrinho(message: types.Message, state: FSMContext):
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
    for item in itens:
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
        texto += f"• {nome}: {qtd}x R${float(valor_unit):.2f} = R${sub:.2f}\n"
        itens_detalhe.append({"nome": nome, "quantidade": qtd, "valor_unitario": valor_unit})

    texto += f"\n💰 *Total: R${total:.2f}*\n\n🏪 Qual o nome do mercado?"
    await state.set_state(MainState.finalizando_mercado)
    await state.update_data(itens_detalhe=itens_detalhe, total=total)
    await message.answer(texto, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())


@dp.message(MainState.finalizando_mercado)
async def finalizar_mercado(message: types.Message, state: FSMContext):
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
    await state.update_data(historico_compras=compras_list)
    await message.answer(f"📜 *Histórico de compras — {dep_nome}*\nSelecione uma compra para ver os detalhes:", parse_mode="Markdown", reply_markup=kb)


@dp.message(MainState.historico_menu)
async def selecionar_historico(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Menu Principal":
        await limpar_estado_preservando_departamento(state)
        await state.set_state(MainState.menu_principal)
        return await message.answer("Menu principal:", reply_markup=kb_menu_principal())

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
        texto += f"• {item['item_nome']}: {item['quantidade']}x R${item['valor_unitario']:.2f} = R${sub:.2f}\n"

    kb_voltar = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⬅️ Voltar Histórico")], [KeyboardButton(text="⬅️ Menu Principal")]],
        resize_keyboard=True,
    )
    await state.set_state(MainState.historico_detalhe)
    await message.answer(texto, parse_mode="Markdown", reply_markup=kb_voltar)


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

    if message.text == "⬅️ Menu Principal":
        await limpar_estado_preservando_departamento(state)
        await state.set_state(MainState.menu_principal)
        return await message.answer("Menu principal:", reply_markup=kb_menu_principal())


# ─── CHAMA ROTERS EXTERNOS (listas) E START ────
async def main():
    # inclui router de listas (import dentro da função para evitar ciclos)
    from listas import router as listas_router
    dp.include_router(listas_router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())