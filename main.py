import asyncio
import os

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from dotenv import load_dotenv

import catalogo
import categorias
import database
import listas
import produtos

load_dotenv()

bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()


class MainState(StatesGroup):
    escolhendo_departamento = State()
    menu_principal = State()
    finalizando_mercado = State()
    confirmando_finalizar = State()
    # Carrinho
    carrinho_menu = State()
    removendo_item = State()
    # Histórico
    historico_menu = State()
    historico_detalhe = State()


class ShopState(StatesGroup):
    navegando = State()
    quantidade = State()
    valor = State()


def kb_departamentos(departamentos):
    btns = []
    for dep in departamentos:
        texto = f"{dep['emoji']} {dep['nome']}" if dep["emoji"] else dep["nome"]
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
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏷️ Categorias"), KeyboardButton(text="📋 Listas")],
            [KeyboardButton(text="📦 Produtos")],
            [KeyboardButton(text="⬅️ Menu Principal")],
        ],
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
        keyboard=[
            [KeyboardButton(text="✅ Confirmar"), KeyboardButton(text="❌ Cancelar")],
        ],
        resize_keyboard=True,
    )


def kb_opcoes(lista, voltar=True):
    btns = [[KeyboardButton(text=catalogo.formatar(opt))] for opt in lista]
    if voltar:
        btns.append([KeyboardButton(text="⬅️ Voltar")])
    btns.append([KeyboardButton(text="❌ Cancelar")])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)


async def extrato_carrinho(message: types.Message, dep_id: int):
    itens = await database.pegar_carrinho(message.from_user.id, dep_id)
    if not itens:
        return False

    texto = "🛒 *Carrinho atual:*\n\n"
    total = 0
    for item in itens:
        sub = item["quantidade"] * item["valor_unitario"]
        total += sub
        texto += (
            f"• {item['item_nome']}: "
            f"{item['quantidade']}x R${item['valor_unitario']:.2f} = R${sub:.2f}\n"
        )

    texto += f"\n💰 *Total: R${total:.2f}*"
    await message.answer(texto, parse_mode="Markdown")
    return True


async def get_dep_data(state: FSMContext):
    data = await state.get_data()
    dep_id = data.get("departamento_id")
    dep_nome = data.get("departamento_nome")
    dep_emoji = data.get("departamento_emoji")
    catalogo_json = data.get("catalogo_json")

    if catalogo_json and not catalogo.CATALOGO:
        catalogo.carregar_catalogo_dep(catalogo_json)

    return dep_id, dep_nome, dep_emoji, catalogo_json


async def limpar_estado_preservando_departamento(state: FSMContext):
    dep_id, dep_nome, dep_emoji, catalogo_json = await get_dep_data(state)
    await state.clear()

    if dep_id:
        await state.set_data(
            {
                "departamento_id": dep_id,
                "departamento_nome": dep_nome,
                "departamento_emoji": dep_emoji,
                "catalogo_json": catalogo_json,
            }
        )


# ─── /start ────

@dp.message(CommandStart())
async def start(message: types.Message, state: FSMContext):
    await database.init_db()
    deps = await database.listar_departamentos()

    if not deps:
        return await message.answer("Nenhum departamento encontrado no banco.")

    await state.clear()
    await state.set_state(MainState.escolhendo_departamento)
    await message.answer(
        "🏬 Escolha o departamento:",
        reply_markup=kb_departamentos(deps),
    )


@dp.message(MainState.escolhendo_departamento)
async def escolher_departamento(message: types.Message, state: FSMContext):
    deps = await database.listar_departamentos()
    escolhido = None

    for dep in deps:
        texto_botao = f"{dep['emoji']} {dep['nome']}" if dep["emoji"] else dep["nome"]
        if message.text == texto_botao or message.text == dep["nome"]:
            escolhido = dep
            break

    if not escolhido:
        return await message.answer("Escolha um departamento válido.")

    catalogo.carregar_catalogo_dep(escolhido["catalogo_json"])

    await state.set_data(
        {
            "departamento_id": escolhido["id"],
            "departamento_nome": escolhido["nome"],
            "departamento_emoji": escolhido["emoji"],
            "catalogo_json": escolhido["catalogo_json"],
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
    dep_id, _, _, _ = await get_dep_data(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento primeiro.")

    await state.set_state(MainState.menu_principal)
    await message.answer("🛒 Menu de Compras:", reply_markup=kb_menu_compras())


@dp.message(F.text == "📲 Cadastros")
async def abrir_cadastros(message: types.Message, state: FSMContext):
    dep_id, _, _, _ = await get_dep_data(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento primeiro.")

    await state.set_state(MainState.menu_principal)
    await message.answer("📲 Menu de Cadastros:", reply_markup=kb_menu_cadastros())


@dp.message(F.text == "⬅️ Menu Principal")
async def voltar_menu_principal(message: types.Message, state: FSMContext):
    dep_id, _, _, _ = await get_dep_data(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento primeiro.")

    await limpar_estado_preservando_departamento(state)
    await state.set_state(MainState.menu_principal)
    await message.answer("Menu principal:", reply_markup=kb_menu_principal())


@dp.message(F.text == "⬅️ Voltar Compras")
async def voltar_compras(message: types.Message, state: FSMContext):
    dep_id, _, _, _ = await get_dep_data(state)
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
    await message.answer(
        "🏬 Escolha o departamento:",
        reply_markup=kb_departamentos(deps),
    )


# ─── COMPRA AVULSA ────

@dp.message(F.text == "🛒 Compra Avulsa")
async def start_buy(message: types.Message, state: FSMContext):
    dep_id, dep_nome, _, _ = await get_dep_data(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento primeiro.")

    await limpar_estado_preservando_departamento(state)
    await state.set_state(ShopState.navegando)
    await state.update_data(caminho=[])

    if not catalogo.CATALOGO:
        return await message.answer("Esse departamento ainda não possui catálogo configurado.")

    opts = list(catalogo.CATALOGO.keys())
    await message.answer(
        f"🛒 Compra avulsa em *{dep_nome}*.\nEscolha a categoria:",
        parse_mode="Markdown",
        reply_markup=kb_opcoes(opts, False),
    )


@dp.message(ShopState.navegando)
async def navegar(message: types.Message, state: FSMContext):
    dep_id, _, _, _ = await get_dep_data(state)
    data = await state.get_data()
    caminho = data.get("caminho", [])

    if not dep_id:
        await state.clear()
        return await message.answer("Envie /start e escolha um departamento primeiro.")

    if message.text == "⬅️ Voltar":
        if not caminho:
            await limpar_estado_preservando_departamento(state)
            await state.set_state(MainState.menu_principal)
            return await message.answer("Menu principal:", reply_markup=kb_menu_principal())

        caminho.pop()
        await state.update_data(caminho=caminho)
        opts = list(catalogo.CATALOGO.keys()) if not caminho else catalogo.obter_opcoes(caminho)
        return await message.answer("Voltando...", reply_markup=kb_opcoes(opts, len(caminho) > 0))

    if message.text == "❌ Cancelar":
        await limpar_estado_preservando_departamento(state)
        await state.set_state(MainState.menu_principal)
        return await message.answer("Operação cancelada.", reply_markup=kb_menu_compras())

    tipo, chave = catalogo.identificar_escolha(caminho, message.text)

    if tipo == "categoria":
        caminho.append(chave)
        await state.update_data(caminho=caminho)
        nova_lista = catalogo.obter_opcoes(caminho)

        if not nova_lista:
            await limpar_estado_preservando_departamento(state)
            await state.set_state(MainState.menu_principal)
            return await message.answer("Categoria vazia.", reply_markup=kb_menu_principal())

        return await message.answer("Selecione:", reply_markup=kb_opcoes(nova_lista))

    if tipo == "produto":
        await state.update_data(produto=chave)
        await state.set_state(ShopState.quantidade)
        return await message.answer(
            f"Quanto de {chave}?",
            reply_markup=ReplyKeyboardRemove(),
        )

    await message.answer("Opção inválida. Use o teclado do bot.")


@dp.message(ShopState.quantidade)
async def set_qtd(message: types.Message, state: FSMContext):
    try:
        qtd = float(message.text.replace(",", "."))
    except ValueError:
        return await message.answer("Por favor, digite um número válido.")

    await state.update_data(qtd=qtd)
    await state.set_state(ShopState.valor)
    await message.answer("Qual o valor unitário? (Ex: 5.50)")


@dp.message(ShopState.valor)
async def set_valor(message: types.Message, state: FSMContext):
    dep_id, _, _, _ = await get_dep_data(state)
    if not dep_id:
        await state.clear()
        return await message.answer("Envie /start e escolha um departamento primeiro.")

    try:
        valor = float(message.text.replace(",", "."))
    except ValueError:
        return await message.answer("Valor inválido.")

    data = await state.get_data()

    await database.adicionar_ao_carrinho(
        message.from_user.id,
        dep_id,
        data["produto"],
        data["qtd"],
        valor,
    )

    await state.set_state(ShopState.navegando)

    await extrato_carrinho(message, dep_id)

    caminho = data.get("caminho", [])
    opts = catalogo.obter_opcoes(caminho) if caminho else list(catalogo.CATALOGO.keys())
    await message.answer(
        "Adicione mais itens ou cancele:",
        reply_markup=kb_opcoes(opts, len(caminho) > 0),
    )


# ─── VER CARRINHO ────

@dp.message(F.text == "📦 Ver Carrinho")
async def ver_carrinho(message: types.Message, state: FSMContext):
    dep_id, _, _, _ = await get_dep_data(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento primeiro.")

    itens = await database.pegar_carrinho(message.from_user.id, dep_id)
    if not itens:
        return await message.answer("🛒 Carrinho vazio!", reply_markup=kb_menu_compras())

    texto = "🛒 *Carrinho Atual:*\n\n"
    total = 0
    for item in itens:
        sub = item["quantidade"] * item["valor_unitario"]
        total += sub
        texto += (
            f"• {item['item_nome']}: "
            f"{item['quantidade']}x R${item['valor_unitario']:.2f} = R${sub:.2f}\n"
        )
    texto += f"\n💰 *TOTAL: R${total:.2f}*"

    await state.set_state(MainState.carrinho_menu)
    await message.answer(texto, parse_mode="Markdown", reply_markup=kb_carrinho_menu())


# ─── REMOVER ITEM DO CARRINHO ────

@dp.message(MainState.carrinho_menu, F.text == "🗑️ Remover Item")
async def remover_item_inicio(message: types.Message, state: FSMContext):
    dep_id, _, _, _ = await get_dep_data(state)
    itens = await database.pegar_carrinho(message.from_user.id, dep_id)

    if not itens:
        return await message.answer("Carrinho já está vazio.")

    btns = [[KeyboardButton(text=item["item_nome"])] for item in itens]
    btns.append([KeyboardButton(text="⬅️ Voltar Carrinho")])
    kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

    await state.set_state(MainState.removendo_item)
    await message.answer("Qual item deseja remover?", reply_markup=kb)


@dp.message(MainState.removendo_item)
async def remover_item_confirmar(message: types.Message, state: FSMContext):
    dep_id, _, _, _ = await get_dep_data(state)

    if message.text == "⬅️ Voltar Carrinho":
        await state.set_state(MainState.carrinho_menu)
        itens = await database.pegar_carrinho(message.from_user.id, dep_id)
        texto = "🛒 *Carrinho Atual:*\n\n"
        total = 0
        for item in itens:
            sub = item["quantidade"] * item["valor_unitario"]
            total += sub
            texto += f"• {item['item_nome']}: {item['quantidade']}x R${item['valor_unitario']:.2f} = R${sub:.2f}\n"
        texto += f"\n💰 *TOTAL: R${total:.2f}*"
        return await message.answer(texto, parse_mode="Markdown", reply_markup=kb_carrinho_menu())

    nome_item = message.text.strip()
    await database.remover_item_carrinho(message.from_user.id, dep_id, nome_item)

    itens = await database.pegar_carrinho(message.from_user.id, dep_id)
    await state.set_state(MainState.carrinho_menu)

    if not itens:
        await message.answer(
            f"✅ *{nome_item}* removido. Carrinho vazio.",
            parse_mode="Markdown",
            reply_markup=kb_menu_compras(),
        )
        await limpar_estado_preservando_departamento(state)
        await state.set_state(MainState.menu_principal)
        return

    texto = f"✅ *{nome_item}* removido.\n\n🛒 *Carrinho Atual:*\n\n"
    total = 0
    for item in itens:
        sub = item["quantidade"] * item["valor_unitario"]
        total += sub
        texto += f"• {item['item_nome']}: {item['quantidade']}x R${item['valor_unitario']:.2f} = R${sub:.2f}\n"
    texto += f"\n💰 *TOTAL: R${total:.2f}*"
    await message.answer(texto, parse_mode="Markdown", reply_markup=kb_carrinho_menu())


# ─── LIMPAR CARRINHO ────

@dp.message(MainState.carrinho_menu, F.text == "🧹 Limpar Carrinho")
async def limpar_carrinho_menu(message: types.Message, state: FSMContext):
    await state.update_data(acao_pendente="limpar")
    await message.answer(
        "⚠️ Tem certeza que deseja limpar todo o carrinho?",
        reply_markup=kb_confirmar(),
    )


@dp.message(MainState.carrinho_menu, F.text == "✅ Confirmar")
async def confirmar_acao_carrinho(message: types.Message, state: FSMContext):
    dep_id, _, _, _ = await get_dep_data(state)
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

        await database.salvar_historico(dep_id, "Compra Avulsa", mercado, itens_detalhe, total)
        await database.limpar_carrinho(message.from_user.id, dep_id)
        await limpar_estado_preservando_departamento(state)
        await state.set_state(MainState.menu_principal)

        await message.answer(
            f"✅ Compra no *{mercado}* finalizada!\n"
            f"💰 Total: R${total:.2f}\n"
            f"📦 {len(itens_detalhe)} itens registrados no histórico.",
            parse_mode="Markdown",
        )
        await message.answer("O que deseja fazer agora?", reply_markup=kb_menu_principal())


@dp.message(MainState.carrinho_menu, F.text == "❌ Cancelar")
async def cancelar_acao_carrinho(message: types.Message, state: FSMContext):
    dep_id, _, _, _ = await get_dep_data(state)
    itens = await database.pegar_carrinho(message.from_user.id, dep_id)

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
    dep_id, _, _, _ = await get_dep_data(state)
    itens = await database.pegar_carrinho(message.from_user.id, dep_id)

    if not itens:
        return await message.answer("Carrinho vazio!", reply_markup=kb_menu_compras())

    texto = "🛒 *Resumo do carrinho:*\n\n"
    total = 0
    itens_detalhe = []

    for item in itens:
        sub = item["quantidade"] * item["valor_unitario"]
        total += sub
        texto += (
            f"• {item['item_nome']}: "
            f"{item['quantidade']}x R${item['valor_unitario']:.2f} = R${sub:.2f}\n"
        )
        itens_detalhe.append(
            {
                "nome": item["item_nome"],
                "quantidade": item["quantidade"],
                "valor_unitario": item["valor_unitario"],
            }
        )

    texto += f"\n💰 *Total: R${total:.2f}*\n\n🏪 Qual o nome do mercado?"

    await state.set_state(MainState.finalizando_mercado)
    await state.update_data(itens_detalhe=itens_detalhe, total=total)
    await message.answer(texto, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())


@dp.message(MainState.finalizando_mercado)
async def finalizar_mercado(message: types.Message, state: FSMContext):
    dep_id, _, _, _ = await get_dep_data(state)
    if not dep_id:
        await state.clear()
        return await message.answer("Envie /start e escolha um departamento primeiro.")

    mercado = message.text.strip()
    data = await state.get_data()
    itens_detalhe = data.get("itens_detalhe", [])
    total = data.get("total", 0)

    # Guarda mercado e pede confirmação
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
        return await message.answer(
            "📜 Nenhuma compra registrada ainda.",
            reply_markup=kb_menu_principal(),
        )

    btns = []
    for c in compras:
        data_fmt = c["data"].strftime("%d/%m/%Y %H:%M") if c["data"] else "?"
        label = f"🏪 {c['mercado']} — R${c['total']:.2f} ({data_fmt})"
        btns.append([KeyboardButton(text=label)])
    btns.append([KeyboardButton(text="⬅️ Menu Principal")])

    kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)
    await state.set_state(MainState.historico_menu)
    await state.update_data(historico_compras=[dict(c) for c in compras])
    await message.answer(
        f"📜 *Histórico de compras — {dep_nome}*\nSelecione uma compra para ver os detalhes:",
        parse_mode="Markdown",
        reply_markup=kb,
    )


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
            data_fmt = c["data"].strftime("%d/%m/%Y %H:%M") if c["data"] else "?"
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


async def main():
    dp.include_router(listas.router)
    dp.include_router(categorias.router)
    dp.include_router(produtos.router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
