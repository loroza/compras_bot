from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

import database
import catalogo

router = Router()

class ListaState(StatesGroup):
    criando_nome = State()
    escolhendo_lista = State()
    navegando_catalogo = State()
    compra_navegando = State()
    compra_quantidade = State()
    compra_valor = State()
    removendo_item = State()
    escolhendo_lista_remover = State()

def kb_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🛒 Compra Avulsa"), KeyboardButton(text="📋 Minhas Listas")],
        [KeyboardButton(text="📦 Ver Carrinho"), KeyboardButton(text="🏁 Finalizar")]
    ], resize_keyboard=True)

def kb_listas_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Nova Lista")],
        [KeyboardButton(text="📝 Adicionar Itens"), KeyboardButton(text="🚀 Iniciar Compra")],
        [KeyboardButton(text="🗑️ Remover Item"), KeyboardButton(text="⬅️ Menu Principal")]
    ], resize_keyboard=True)

def kb_opcoes(lista, voltar=True):
    btns = [[KeyboardButton(text=catalogo.formatar(opt))] for opt in lista]
    if voltar:
        btns.append([KeyboardButton(text="⬅️ Voltar")])
    btns.append([KeyboardButton(text="❌ Cancelar")])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

def kb_lista_escolha(listas):
    btns = [[KeyboardButton(text=nome)] for nome in listas]
    btns.append([KeyboardButton(text="❌ Cancelar")])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

def obter_opcoes_nivel(caminho):
    if not caminho:
        return list(catalogo.CATALOGO.keys())
    return catalogo.obter_opcoes(caminho)


# ─── MENU LISTAS ────────────────────────────────────────────────────────────

@router.message(F.text == "📋 Minhas Listas")
async def menu_listas(message: types.Message):
    await message.answer("📋 Gerenciador de Listas:", reply_markup=kb_listas_menu())

@router.message(F.text == "⬅️ Menu Principal")
async def voltar_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Menu Principal:", reply_markup=kb_menu())


# ─── CRIAR LISTA ────────────────────────────────────────────────────────────

@router.message(F.text == "➕ Nova Lista")
async def nova_lista(message: types.Message, state: FSMContext):
    await state.set_state(ListaState.criando_nome)
    await message.answer("Digite o nome da nova lista:\n(Ex: Mensal, Churrasco, Feira)", reply_markup=ReplyKeyboardRemove())

@router.message(ListaState.criando_nome)
async def salvar_nome_lista(message: types.Message, state: FSMContext):
    nome = message.text.strip()
    criado = await database.criar_lista(nome)
    await state.clear()
    if criado:
        await message.answer(f"✅ Lista *{nome}* criada com sucesso!", reply_markup=kb_listas_menu(), parse_mode="Markdown")
    else:
        await message.answer(f"⚠️ Já existe uma lista com o nome *{nome}*.", reply_markup=kb_listas_menu(), parse_mode="Markdown")


# ─── ADICIONAR ITENS À LISTA ────────────────────────────────────────────────

@router.message(F.text == "📝 Adicionar Itens")
async def adicionar_itens(message: types.Message, state: FSMContext):
    listas = await database.pegar_listas_disponiveis()
    if not listas:
        return await message.answer("Nenhuma lista criada ainda. Crie uma primeiro!", reply_markup=kb_listas_menu())
    await state.set_state(ListaState.escolhendo_lista)
    await state.update_data(modo="adicionar")
    await message.answer("Qual lista você quer editar?", reply_markup=kb_lista_escolha(listas))

@router.message(ListaState.escolhendo_lista)
async def lista_escolhida(message: types.Message, state: FSMContext):
    if message.text == "❌ Cancelar":
        await state.clear()
        return await message.answer("Cancelado.", reply_markup=kb_listas_menu())

    data = await state.get_data()
    modo = data.get("modo")
    listas = await database.pegar_listas_disponiveis()

    if message.text not in listas:
        return await message.answer("Lista não encontrada. Tente novamente.", reply_markup=kb_lista_escolha(listas))

    if modo == "adicionar":
        await state.set_state(ListaState.navegando_catalogo)
        await state.update_data(lista_atual=message.text, caminho=[])
        opts = list(catalogo.CATALOGO.keys())
        await message.answer(
            f"📝 Adicionando itens em *{message.text}*\nEscolha a categoria:",
            reply_markup=kb_opcoes(opts, False),
            parse_mode="Markdown"
        )

    elif modo == "compra":
        itens = await database.pegar_itens_da_lista(message.text)
        if not itens:
            await state.clear()
            return await message.answer("Essa lista está vazia! Adicione itens primeiro.", reply_markup=kb_listas_menu())

        await database.limpar_carrinho(message.from_user.id)
        await state.set_state(ListaState.compra_navegando)
        await state.update_data(
            lista_atual=message.text,
            itens_lista=itens,
            itens_comprados=[],
            caminho_compra=[]
        )

        categorias = catalogo.obter_opcoes([])
        btns = [[KeyboardButton(text=catalogo.formatar(c))] for c in categorias]
        btns.append([KeyboardButton(text="✅ Finalizar Compra")])
        kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

        await message.answer(
            f"🛒 Compra da lista *{message.text}* iniciada!\n"
            f"📋 {len(itens)} itens pendentes\n\n"
            f"Navegue pelas categorias:",
            reply_markup=kb,
            parse_mode="Markdown"
        )


# ─── INICIAR COMPRA ─────────────────────────────────────────────────────────

@router.message(F.text == "🚀 Iniciar Compra")
async def iniciar_compra(message: types.Message, state: FSMContext):
    listas = await database.pegar_listas_disponiveis()
    if not listas:
        return await message.answer("Nenhuma lista criada ainda!", reply_markup=kb_listas_menu())
    await state.set_state(ListaState.escolhendo_lista)
    await state.update_data(modo="compra")
    await message.answer("Qual lista você quer usar?", reply_markup=kb_lista_escolha(listas))

@router.message(F.text == "🚀 Iniciar Compra")
async def iniciar_compra(message: types.Message, state: FSMContext):
    listas = await database.pegar_listas_disponiveis()
    if not listas:
        return await message.answer("Nenhuma lista criada ainda!", reply_markup=kb_listas_menu())
    await state.set_state(ListaState.escolhendo_lista)
    await state.update_data(modo="compra")
    await message.answer("Qual lista você quer usar?", reply_markup=kb_lista_escolha(listas))


# ─── NAVEGAÇÃO DURANTE A COMPRA ─────────────────────────────────────────────

@router.message(ListaState.compra_navegando)
async def compra_navegar(message: types.Message, state: FSMContext):
    data = await state.get_data()
    caminho = data.get("caminho_compra", [])
    itens_lista = data.get("itens_lista", [])
    itens_comprados = data.get("itens_comprados", [])

    if message.text == "✅ Finalizar Compra":
        pendentes = [i for i in itens_lista if i not in itens_comprados]
        if pendentes:
            texto = "⚠️ Itens ainda não comprados:\n" + "\n".join(f"• {i}" for i in pendentes)
            texto += "\n\nDeseja finalizar mesmo assim?"
            kb = ReplyKeyboardMarkup(keyboard=[
                [KeyboardButton(text="✅ Sim, finalizar"), KeyboardButton(text="🔙 Voltar")]
            ], resize_keyboard=True)
            return await message.answer(texto, reply_markup=kb)
        await state.clear()
        return await message.answer("✅ Compra finalizada!", reply_markup=kb_listas_menu())

    if message.text == "✅ Sim, finalizar":
        await state.clear()
        return await message.answer("✅ Compra finalizada!", reply_markup=kb_listas_menu())

    if message.text == "🔙 Voltar":
        if caminho:
            caminho.pop()
        await state.update_data(caminho_compra=caminho)
        return await _mostrar_nivel_compra(message, state, caminho, itens_lista, itens_comprados)

    tipo, chave = catalogo.identificar_escolha(caminho, message.text)

    if tipo == "categoria":
        caminho.append(chave)
        await state.update_data(caminho_compra=caminho)
        return await _mostrar_nivel_compra(message, state, caminho, itens_lista, itens_comprados)

    elif tipo == "produto":
        pendentes = [i for i in itens_lista if i not in itens_comprados]
        if chave not in pendentes:
            return await message.answer("Este item já foi comprado ou não está na lista.")
        await state.update_data(item_atual=chave)
        await state.set_state(ListaState.compra_quantidade)
        return await message.answer(f"🛍️ *{chave}*\nQual a quantidade?", parse_mode="Markdown")

    else:
        await message.answer("Opção inválida. Use o teclado do bot.")


async def _mostrar_nivel_compra(message, state, caminho, itens_lista, itens_comprados):
    opcoes = catalogo.obter_opcoes(caminho)
    pendentes = [i for i in itens_lista if i not in itens_comprados]

    if not opcoes or not caminho:
        categorias = catalogo.obter_opcoes([])
        btns = [[KeyboardButton(text=catalogo.formatar(c))] for c in categorias]
        btns.append([KeyboardButton(text="✅ Finalizar Compra")])
        kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)
        return await message.answer("Escolha a categoria:", reply_markup=kb)

    primeira = opcoes[0] if opcoes else None
    no_teste = catalogo.obter_no(caminho + [primeira]) if primeira else None

    if no_teste is None:
        # Nível de produtos — filtra só os pendentes da lista
        itens_aqui = [p for p in opcoes if p in pendentes]
        if not itens_aqui:
            await message.answer("✅ Todos os itens desta categoria já foram comprados!")
            if caminho:
                caminho.pop()
            await state.update_data(caminho_compra=caminho)
            categorias = catalogo.obter_opcoes([])
            btns = [[KeyboardButton(text=catalogo.formatar(c))] for c in categorias]
            btns.append([KeyboardButton(text="✅ Finalizar Compra")])
            kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)
            return await message.answer("Escolha outra categoria:", reply_markup=kb)

        btns = [[KeyboardButton(text=item)] for item in itens_aqui]
        btns.append([KeyboardButton(text="🔙 Voltar")])
        kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)
        await message.answer(f"📋 Itens pendentes aqui ({len(itens_aqui)}):", reply_markup=kb)
    else:
        # Nível de subcategorias/grupos
        btns = [[KeyboardButton(text=catalogo.formatar(c))] for c in opcoes]
        btns.append([KeyboardButton(text="🔙 Voltar")])
        kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)
        await message.answer("Selecione:", reply_markup=kb)


# ─── QUANTIDADE E VALOR DURANTE COMPRA ──────────────────────────────────────

@router.message(ListaState.compra_quantidade)
async def compra_qtd(message: types.Message, state: FSMContext):
    try:
        qtd = float(message.text.replace(",", "."))
    except ValueError:
        return await message.answer("Digite um número válido. Ex: 2 ou 1.5")
    await state.update_data(qtd_atual=qtd)
    await state.set_state(ListaState.compra_valor)
    await message.answer("💰 Qual o valor unitário? (Ex: 12.90)")

@router.message(ListaState.compra_valor)
async def compra_val(message: types.Message, state: FSMContext):
    try:
        valor = float(message.text.replace(",", "."))
    except ValueError:
        return await message.answer("Digite um valor válido. Ex: 12.90")

    data = await state.get_data()
    item = data["item_atual"]
    qtd = data["qtd_atual"]
    caminho = data.get("caminho_compra", [])
    itens_lista = data.get("itens_lista", [])
    itens_comprados = data.get("itens_comprados", [])

    await database.adicionar_ao_carrinho(message.from_user.id, item, qtd, valor)
    itens_comprados.append(item)
    await state.update_data(itens_comprados=itens_comprados)
    await state.set_state(ListaState.compra_navegando)

    pendentes = [i for i in itens_lista if i not in itens_comprados]
    await message.answer(
        f"✅ *{item}* adicionado!\n"
        f"Qtd: {qtd} | Valor: R$ {valor:.2f} | Total: R$ {qtd * valor:.2f}\n\n"
        f"📋 Ainda faltam {len(pendentes)} itens",
        parse_mode="Markdown"
    )
    await _mostrar_nivel_compra(message, state, caminho, itens_lista, itens_comprados)


# ─── NAVEGAÇÃO NO CATÁLOGO PARA ADICIONAR ITEM À LISTA ──────────────────────

@router.message(ListaState.navegando_catalogo)
async def navegar_catalogo_lista(message: types.Message, state: FSMContext):
    data = await state.get_data()
    caminho = data.get("caminho", [])
    lista_atual = data.get("lista_atual")

    if message.text == "⬅️ Voltar":
        if not caminho:
            await state.set_state(ListaState.escolhendo_lista)
            listas = await database.pegar_listas_disponiveis()
            return await message.answer("Escolha a lista:", reply_markup=kb_lista_escolha(listas))
        caminho.pop()
        await state.update_data(caminho=caminho)
        opts = obter_opcoes_nivel(caminho)
        return await message.answer("Voltando...", reply_markup=kb_opcoes(opts, len(caminho) > 0))

    if message.text == "❌ Cancelar":
        await state.clear()
        return await message.answer(f"✅ Itens salvos em *{lista_atual}*!", reply_markup=kb_listas_menu(), parse_mode="Markdown")

    tipo, valor = catalogo.identificar_escolha(caminho, message.text)

    if tipo == "produto":
        await database.adicionar_item_lista(lista_atual, valor)
        opts = obter_opcoes_nivel(caminho)
        await message.answer(f"✅ *{valor}* adicionado!", reply_markup=kb_opcoes(opts, len(caminho) > 0), parse_mode="Markdown")

    elif tipo == "categoria":
        caminho.append(valor)
        await state.update_data(caminho=caminho)
        novas_opts = obter_opcoes_nivel(caminho)
        await message.answer(f"📂 {message.text}:", reply_markup=kb_opcoes(novas_opts))

    else:
        await message.answer("Opção inválida. Use o teclado do bot.")


# ─── REMOVER ITEM DA LISTA ───────────────────────────────────────────────────

@router.message(F.text == "🗑️ Remover Item")
async def cmd_remover(message: types.Message, state: FSMContext):
    listas = await database.pegar_listas_disponiveis()
    if not listas:
        return await message.answer("Nenhuma lista criada ainda!", reply_markup=kb_listas_menu())
    await state.set_state(ListaState.escolhendo_lista_remover)
    await message.answer("De qual lista você quer remover um item?", reply_markup=kb_lista_escolha(listas))

@router.message(ListaState.escolhendo_lista_remover)
async def lista_para_remover(message: types.Message, state: FSMContext):
    if message.text == "❌ Cancelar":
        await state.clear()
        return await message.answer("Cancelado.", reply_markup=kb_listas_menu())

    itens = await database.pegar_itens_da_lista(message.text)
    if not itens:
        await state.clear()
        return await message.answer("Essa lista está vazia!", reply_markup=kb_listas_menu())

    await state.set_state(ListaState.removendo_item)
    await state.update_data(lista_atual=message.text)

    btns = [[KeyboardButton(text=item)] for item in itens]
    btns.append([KeyboardButton(text="❌ Cancelar")])
    kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)
    await message.answer(f"📋 *{message.text}* — Qual item deseja remover?", reply_markup=kb, parse_mode="Markdown")

@router.message(ListaState.removendo_item)
async def confirmar_remocao(message: types.Message, state: FSMContext):
    if message.text == "❌ Cancelar":
        await state.clear()
        return await message.answer("Cancelado.", reply_markup=kb_listas_menu())

    data = await state.get_data()
    lista_atual = data.get("lista_atual")
    await database.remover_item_lista(lista_atual, message.text)

    itens = await database.pegar_itens_da_lista(lista_atual)
    if not itens:
        await state.clear()
        await message.answer(f"🗑️ *{message.text}* removido!\n\nA lista ficou vazia.", reply_markup=kb_listas_menu(), parse_mode="Markdown")
    else:
        btns = [[KeyboardButton(text=item)] for item in itens]
        btns.append([KeyboardButton(text="❌ Cancelar")])
        kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)
        await message.answer(
            f"🗑️ *{message.text}* removido!\n\nRemova outro ou clique em ❌ Cancelar:",
            reply_markup=kb,
            parse_mode="Markdown"
        )