import asyncio
import os
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


# --- HANDLERS ---
@dp.message(CommandStart())
async def start(message: types.Message, state: FSMContext):
    # garante que tabela/departamentos existam
    await database.init_db()

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
    catalogo.carregar_catalogo_dep(escolhido.get("catalogo_json"))

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
    await message.answer("Escolha a categoria:", reply_markup=kb_opcoes(opts, False))


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
        qtd = float(message.text.replace(",", "."))
        await state.update_data(qtd=qtd)
        await state.set_state(ShopState.valor)
        await message.answer("Qual o valor unitário? (Ex: 5.50)")
    except Exception:
        await message.answer("Por favor, digite um número válido.")


@dp.message(ShopState.valor)
async def set_valor(message: types.Message, state: FSMContext):
    try:
        valor = float(message.text.replace(",", "."))
        data = await state.get_data()
        produto = data.get("produto")
        qtd = data.get("qtd")
        dep_id, *_ = await get_dep_data(state)
        if not dep_id:
            return await message.answer("Envie /start e escolha um departamento primeiro.")
        # adiciona ao carrinho (mantendo a assinatura existente)
        await database.adicionar_ao_carrinho(message.from_user.id, dep_id, produto, qtd, valor)

        # NÃO limpar o estado: voltar para navegação para permitir adicionar mais itens
        await state.set_state(ShopState.navegando)
        await state.update_data(caminho=[])

        opts = list(catalogo.CATALOGO.keys())
        return await message.answer(
            f"✅ {catalogo.formatar(produto)} adicionado! Deseja adicionar mais itens?",
            reply_markup=kb_opcoes(opts, False),
        )
    except Exception:
        await message.answer("Valor inválido.")


# ─── VER CARRINHO ────
@dp.message(F.text == "📦 Ver Carrinho")
async def ver_carrinho(message: types.Message, state: FSMContext):
    dep_id, _, _, _ = await get_dep_data(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento primeiro.")
    itens = await database.pegar_carrinho(message.from_user.id, dep_id)
    if not itens:
        return await message.answer("Carrinho vazio!", reply_markup=kb_menu_compras())
    texto = "🛒 *Carrinho Atual:*\n\n"
    total = 0
    for item in itens:
        sub = item["quantidade"] * item["valor_unitario"]
        total += sub
        texto += f"• {item['item_nome']}: {item['quantidade']}x R${item['valor_unitario']:.2f} = R${sub:.2f}\n"
    texto += f"\n💰 *TOTAL: R${total:.2f}*"
    await state.set_state(MainState.carrinho_menu)
    await message.answer(texto, parse_mode="Markdown", reply_markup=kb_carrinho_menu())


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
        await database.limpar_carrinho(message.from_user.id, dep_id)
        await limpar_estado_preservando_departamento(state)
        await state.set_state(MainState.menu_principal)
        await message.answer("🧹 Carrinho limpo!", reply_markup=kb_menu_compras())

    elif acao == "finalizar":
        mercado = data.get("mercado_pendente", "Não informado")
        itens_detalhe = data.get("itens_detalhe", [])
        total = data.get("total", 0)

        await database.salvar_historico(dep_id, data.get("lista_nome", "Compra Avulsa"), mercado, itens_detalhe, total)
        await database.limpar_carrinho(message.from_user.id, dep_id)
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
    itens = await database.pegar_carrinho(message.from_user.id, dep_id)
    if not itens:
        return await message.answer("Carrinho vazio!", reply_markup=kb_menu_compras())
    texto = "🛒 *Carrinho Atual:*\n\n"
    total = 0
    for item in itens:
        sub = item["quantidade"] * item["valor_unitario"]
        total += sub
        texto += f"• {item['item_nome']}: {item['quantidade']}x R${item['valor_unitario']:.2f} = R${sub:.2f}\n"
    texto += f"\n💰 *TOTAL: R${total:.2f}*"
    await message.answer(texto, parse_mode="Markdown", reply_markup=kb_carrinho_menu())


# ─── FINALIZAR COMPRA (via carrinho) ────
@dp.message(MainState.carrinho_menu, F.text == "🏁 Finalizar Compra")
async def finalizar_do_carrinho(message: types.Message, state: FSMContext):
    dep_id, *_ = await get_dep_data(state)
    itens = await database.pegar_carrinho(message.from_user.id, dep_id)
    if not itens:
        return await message.answer("Carrinho vazio!", reply_markup=kb_menu_compras())

    texto = "🛒 *Resumo do carrinho:*\n\n"
    total = 0
    itens_detalhe = []
    for item in itens:
        sub = item["quantidade"] * item["valor_unitario"]
        total += sub
        texto += f"• {item['item_nome']}: {item['quantidade']}x R${item['valor_unitario']:.2f} = R${sub:.2f}\n"
        itens_detalhe.append({"nome": item["item_nome"], "quantidade": item["quantidade"], "valor_unitario": item["valor_unitario"]})

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