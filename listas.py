from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
import catalogo
import database

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


# --- KEYBOARDS ---
def kb_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛒 Compra Avulsa"), KeyboardButton(text="📋 Minhas Listas")],
            [KeyboardButton(text="📦 Ver Carrinho"), KeyboardButton(text="🏁 Finalizar")],
        ],
        resize_keyboard=True,
    )


def kb_listas_menu(allow_iniciar: bool = True):
    """
    Retorna teclado de gerenciamento de listas.
    Se allow_iniciar == False, não inclui o botão '🚀 Iniciar Compra'.
    """
    rows = [
        [KeyboardButton(text="➕ Nova Lista")],
        [KeyboardButton(text="📝 Adicionar Itens")],
    ]
    if allow_iniciar:
        rows[-1].append(KeyboardButton(text="🚀 Iniciar Compra"))

    rows.append([KeyboardButton(text="🗑️ Remover Item"), KeyboardButton(text="⬅️ Menu Principal")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def kb_opcoes(lista, voltar: bool = True):
    """
    Lista de opções do catálogo.
    Se voltar == True, inclui o botão '⬅️ Voltar' (sobe um nível ou sai do fluxo).
    """
    btns = [[KeyboardButton(text=catalogo.formatar(opt))] for opt in lista]
    if voltar:
        btns.append([KeyboardButton(text="⬅️ Voltar")])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)


def kb_lista_escolha(listas):
    btns = [[KeyboardButton(text=l["nome"])] for l in listas]
    btns.append([KeyboardButton(text="⬅️ Voltar")])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)


# --- HELPERS (locais, sem importar main para evitar ciclos) ---
async def get_dep_from_state(state: FSMContext):
    data = await state.get_data()
    return data.get("departamento_id"), data.get("departamento_nome")


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


def montar_extrato_texto(itens: list) -> str:
    """
    Wrapper para chamar a função de catalogo e garantir tamanho/markup adequado.
    """
    return catalogo.formatar_extrato(itens)


def encontrar_item_raw_por_label(itens: list, label: str):
    """
    Converte o texto exibido no botão de volta para o valor real salvo no banco.
    """
    for item in itens:
        if catalogo.formatar(item) == label:
            return item
    return None


# --- HANDLERS ---

# Handler para o módulo de COMPRAS — ao clicar em "📋 Minhas Listas" partimos direto para INICIAR COMPRA
@router.message(F.text == "📋 Minhas Listas")
async def listas_minhas_compras(message: types.Message, state: FSMContext):
    dep_id, _ = await get_dep_from_state(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento primeiro.")
    listas = await database.pegar_listas_disponiveis(dep_id)
    if not listas:
        return await message.answer("Não há listas. Crie uma lista primeiro!", reply_markup=kb_listas_menu(allow_iniciar=False))
    await state.set_state(ListaState.escolhendo_lista)
    await state.update_data(acao="iniciar_compra")
    await message.answer("Selecione a lista para iniciar a compra:", reply_markup=kb_lista_escolha(listas))


# Handler para o módulo de CADASTROS — ao clicar em "📋 Listas" abrimos o gerenciador sem botão "Iniciar Compra"
@router.message(F.text == "📋 Listas")
async def listas_cadastros_manager(message: types.Message, state: FSMContext):
    dep_id, _ = await get_dep_from_state(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento primeiro.")
    await message.answer("Gerenciar Listas:", reply_markup=kb_listas_menu(allow_iniciar=False))


@router.message(F.text == "⬅️ Menu Principal")
async def back_main(message: types.Message, state: FSMContext):
    await limpar_estado_preservando_departamento(state)
    await message.answer("Menu Principal:", reply_markup=kb_menu())


@router.message(F.text == "➕ Nova Lista")
async def new_list(message: types.Message, state: FSMContext):
    dep_id, _ = await get_dep_from_state(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento primeiro.")
    await state.set_state(ListaState.criando_nome)
    await message.answer("Nome da lista:", reply_markup=ReplyKeyboardRemove())


@router.message(ListaState.criando_nome)
async def save_list(message: types.Message, state: FSMContext):
    dep_id, _ = await get_dep_from_state(state)
    if not dep_id:
        await state.clear()
        return await message.answer("Envie /start e escolha um departamento primeiro.")
    sucesso = await database.criar_lista(dep_id, message.text)
    await state.clear()
    if sucesso:
        await message.answer(f"✅ Lista {message.text} criada!", reply_markup=kb_listas_menu())
    else:
        await message.answer("❌ Não foi possível criar a lista (nome já existe?).", reply_markup=kb_listas_menu())


@router.message(F.text == "📝 Adicionar Itens")
async def add_item_start(message: types.Message, state: FSMContext):
    dep_id, _ = await get_dep_from_state(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento primeiro.")
    listas = await database.pegar_listas_disponiveis(dep_id)
    if not listas:
        return await message.answer("Crie uma lista primeiro!", reply_markup=kb_listas_menu())
    await state.set_state(ListaState.escolhendo_lista)
    await state.update_data(acao="adicionar")
    await message.answer("Selecione a lista:", reply_markup=kb_lista_escolha(listas))


@router.message(ListaState.escolhendo_lista)
async def list_chosen(message: types.Message, state: FSMContext):
    # tratar "⬅️ Voltar" como retorno ao menu de listas/encerramento do fluxo
    if message.text == "⬅️ Voltar":
        await state.clear()
        return await message.answer("Cancelado.", reply_markup=kb_listas_menu())

    data = await state.get_data()
    dep_id, _ = await get_dep_from_state(state)
    if not dep_id:
        await state.clear()
        return await message.answer("Envie /start e escolha um departamento primeiro.")

    lista_nome = message.text
    lista_row = await database.buscar_lista_por_nome(dep_id, lista_nome)
    if not lista_row:
        await state.clear()
        return await message.answer("Lista não encontrada.", reply_markup=kb_listas_menu())

    # branch por ação
    if data.get("acao") == "adicionar":
        # mostrar extrato da lista antes de iniciar a navegação no catálogo
        itens = await database.pegar_itens_da_lista(lista_row["id"])
        extrato = montar_extrato_texto(itens)
        await message.answer(f"Extrato atual da lista *{lista_nome}*:\n\n{extrato}", parse_mode="Markdown")
        # inicia navegação no catálogo para adicionar itens
        await state.set_state(ListaState.navegando_catalogo)
        await state.update_data(caminho=[], lista_nome=lista_nome)
        opts = list(catalogo.CATALOGO.keys())
        # mostrar categorias com botão Voltar
        return await message.answer("Escolha a categoria:", reply_markup=kb_opcoes(opts, True))

    # caso iniciar compra
    itens = await database.pegar_itens_da_lista(lista_row["id"])
    if not itens:
        await state.clear()
        return await message.answer("Lista vazia!", reply_markup=kb_listas_menu())
    await state.set_state(ListaState.compra_navegando)
    await state.update_data(itens_pendentes=itens, caminho=[])
    return await message.answer(f"Iniciando compra: {lista_nome}", reply_markup=kb_opcoes(list(catalogo.CATALOGO.keys()), True))


@router.message(ListaState.navegando_catalogo)
async def nav_add(message: types.Message, state: FSMContext):
    data = await state.get_data()
    caminho = data.get("caminho", [])

    # "⬅️ Voltar":
    # - se estamos em um nível interno do catálogo -> sobe um nível (pop)
    # - se estamos no topo (caminho vazio) -> encerra o fluxo de adicionar itens e volta ao menu de listas
    if message.text == "⬅️ Voltar":
        if not caminho:
            # encerrar fluxo de adicionar itens
            await state.clear()
            return await message.answer("Operação finalizada.", reply_markup=kb_listas_menu())
        caminho.pop()
        await state.update_data(caminho=caminho)
        opts = list(catalogo.CATALOGO.keys()) if not caminho else catalogo.obter_opcoes(caminho)
        # sempre mostrar '⬅️ Voltar' nas categorias
        return await message.answer("Selecione:", reply_markup=kb_opcoes(opts, True))

    escolha = message.text.strip()
    tipo, chave = catalogo.identificar_escolha(caminho, escolha)

    if tipo == "categoria":
        caminho.append(chave)
        await state.update_data(caminho=caminho)
        await message.answer("Selecione:", reply_markup=kb_opcoes(catalogo.obter_opcoes(caminho), True))
        return

    if tipo == "produto":
        dep_id, _ = await get_dep_from_state(state)
        lista_nome = data.get("lista_nome")
        if not lista_nome:
            return await message.answer("Lista não encontrada no estado. Reabra o fluxo.")
        lista_row = await database.buscar_lista_por_nome(dep_id, lista_nome)
        if not lista_row:
            return await message.answer("Lista não encontrada no banco.")
        # adiciona o item
        await database.adicionar_item_lista(lista_row["id"], chave)

        # envia extrato atualizado
        itens_atualizados = await database.pegar_itens_da_lista(lista_row["id"])
        extrato = montar_extrato_texto(itens_atualizados)
        await message.answer(f"✅ {catalogo.formatar(chave)} adicionado à lista *{lista_nome}*!\n\nExtrato atualizado:\n\n{extrato}", parse_mode="Markdown")

        # NÃO resetar 'caminho' — permanece no mesmo nível para poder adicionar mais itens naquele lugar
        caminho_atual = data.get("caminho", [])
        opts = list(catalogo.CATALOGO.keys()) if not caminho_atual else catalogo.obter_opcoes(caminho_atual)
        await state.set_state(ListaState.navegando_catalogo)
        await state.update_data(caminho=caminho_atual, lista_nome=lista_nome)
        return await message.answer("Deseja adicionar mais itens? Selecione:", reply_markup=kb_opcoes(opts, True))

    await message.answer("Escolha inválida.")


# --- FLUXO: iniciar compra a partir da lista (itens_pendentes) ---
@router.message(ListaState.compra_navegando)
async def compra_navegar(message: types.Message, state: FSMContext):
    # permitir '⬅️ Voltar' para cancelar compra (voltar ao menu de listas)
    if message.text == "⬅️ Voltar":
        await state.clear()
        return await message.answer("Compra cancelada.", reply_markup=kb_listas_menu())

    data = await state.get_data()
    caminho = data.get("caminho", [])
    itens_pendentes = data.get("itens_pendentes", [])

    if message.text == "❌ Cancelar":
        await state.clear()
        return await message.answer("Operação cancelada.", reply_markup=kb_listas_menu())

    escolha = message.text.strip()
    tipo, chave = catalogo.identificar_escolha(caminho, escolha)
    if tipo == "categoria":
        caminho.append(chave)
        await state.update_data(caminho=caminho)
        await message.answer("Selecione:", reply_markup=kb_opcoes(catalogo.obter_opcoes(caminho), True))
        return

    if tipo == "produto":
        produto = chave
        await state.update_data(produto=produto)
        await state.set_state(ListaState.compra_quantidade)
        await message.answer(f"Quanto de {catalogo.formatar(produto)}?", reply_markup=ReplyKeyboardRemove())
        return

    await message.answer("Escolha inválida.")


@router.message(ListaState.compra_quantidade)
async def compra_set_qtd(message: types.Message, state: FSMContext):
    try:
        qtd = float(message.text.replace(",", "."))
        await state.update_data(qtd=qtd)
        await state.set_state(ListaState.compra_valor)
        await message.answer("Qual o valor unitário? (Ex: 5.50)")
    except Exception:
        await message.answer("Por favor, digite um número válido.")


@router.message(ListaState.compra_valor)
async def compra_set_valor(message: types.Message, state: FSMContext):
    try:
        valor = float(message.text.replace(",", "."))
        data = await state.get_data()
        produto = data.get("produto")
        qtd = data.get("qtd")
        dep_id, _ = await get_dep_from_state(state)
        if not dep_id:
            await state.clear()
            return await message.answer("Envie /start e escolha um departamento primeiro.")
        # adiciona ao carrinho do usuário
        await database.adicionar_ao_carrinho(message.from_user.id, dep_id, produto, qtd, valor)

        # remove item pendente equivalente (se presente)
        itens_pendentes = data.get("itens_pendentes", [])
        if produto in itens_pendentes:
            itens_pendentes.remove(produto)

        # atualiza estado
        await state.update_data(itens_pendentes=itens_pendentes)
        if itens_pendentes:
            await state.set_state(ListaState.compra_navegando)
            await state.update_data(caminho=[])
            await message.answer(f"✅ {catalogo.formatar(produto)} adicionado! Próximo item:", reply_markup=kb_opcoes(list(catalogo.CATALOGO.keys()), True))
        else:
            await state.clear()
            await message.answer("✅ Todos os itens da lista foram adicionados ao carrinho!", reply_markup=kb_listas_menu())
    except Exception:
        await message.answer("Valor inválido.")


# Remoção de item (simples)
@router.message(F.text == "🗑️ Remover Item")
async def remover_item_start(message: types.Message, state: FSMContext):
    dep_id, _ = await get_dep_from_state(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento primeiro.")
    listas = await database.pegar_listas_disponiveis(dep_id)
    if not listas:
        return await message.answer("Não há listas para remover itens.", reply_markup=kb_listas_menu())
    await state.set_state(ListaState.escolhendo_lista_remover)
    await message.answer("Selecione a lista:", reply_markup=kb_lista_escolha(listas))


@router.message(ListaState.escolhendo_lista_remover)
async def remover_item_lista_handler(message: types.Message, state: FSMContext):
    dep_id, _ = await get_dep_from_state(state)
    if message.text == "⬅️ Voltar":
        await state.clear()
        return await message.answer("Operação cancelada.", reply_markup=kb_listas_menu())

    lista_row = await database.buscar_lista_por_nome(dep_id, message.text)
    if not lista_row:
        await state.clear()
        return await message.answer("Lista não encontrada.", reply_markup=kb_listas_menu())

    itens = await database.pegar_itens_da_lista(lista_row["id"])
    if not itens:
        await state.clear()
        return await message.answer("Lista vazia.", reply_markup=kb_listas_menu())

    btns = [[KeyboardButton(text=catalogo.formatar(i))] for i in itens]
    btns.append([KeyboardButton(text="⬅️ Voltar")])
    kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)
    await state.set_state(ListaState.removendo_item)
    await state.update_data(lista_id=lista_row["id"], lista_nome=lista_row["nome"], departamento_id=dep_id)
    await message.answer("Selecione o item para remover:", reply_markup=kb)


@router.message(ListaState.removendo_item)
async def confirmar_remover_item(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lista_id = data.get("lista_id")
    lista_nome = data.get("lista_nome")
    dep_id = data.get("departamento_id")

    # voltar para a seleção da lista (não encerrar)
    if message.text == "⬅️ Voltar":
        listas = await database.pegar_listas_disponiveis(dep_id)
        await state.set_state(ListaState.escolhendo_lista_remover)
        return await message.answer("Selecione a lista:", reply_markup=kb_lista_escolha(listas))

    itens_atuais = await database.pegar_itens_da_lista(lista_id)
    item_raw = encontrar_item_raw_por_label(itens_atuais, message.text)

    if not item_raw:
        return await message.answer("Item não encontrado. Selecione um item válido.")

    # remover no banco
    await database.remover_item_lista(lista_id, item_raw)

    # reconsultar itens restantes depois da remoção
    itens_restantes = await database.pegar_itens_da_lista(lista_id)

    if not itens_restantes:
        # agora VOLTAR ao menu anterior (seleção de listas) em vez de finalizar/limpar o estado
        listas = await database.pegar_listas_disponiveis(dep_id)
        await state.set_state(ListaState.escolhendo_lista_remover)
        return await message.answer(
            f"✅ {catalogo.formatar(item_raw)} removido da lista *{lista_nome}*.\n\nA lista está vazia. Selecione outra lista:",
            reply_markup=kb_lista_escolha(listas)
        )

    btns = [[KeyboardButton(text=catalogo.formatar(i))] for i in itens_restantes]
    btns.append([KeyboardButton(text="⬅️ Voltar")])
    kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

    await state.set_state(ListaState.removendo_item)
    await state.update_data(lista_id=lista_id, lista_nome=lista_nome, departamento_id=dep_id)

    return await message.answer(
        f"✅ {catalogo.formatar(item_raw)} removido.\n\nSelecione outro item para remover:",
        reply_markup=kb
    )