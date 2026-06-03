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
    Se voltar == True, inclui o botão '⬅️ Voltar' (sobe um nível ou volta à seleção de listas).
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


# --- HELPERS PARA FILTRAR CATEGORIAS E SUBCATEGORIAS PELO CONTEÚDO DA LISTA ---
def _buscar_produto_recursivo(no, produto):
    """
    Retorna True se 'produto' existir no nó 'no' (varre recursivamente).
    Suporta nós em formato dict com chaves comuns: 'produtos', 'subcategorias', 'grupos',
    ou listas diretamente.
    """
    if isinstance(no, dict):
        # checa lista direta de produtos no nó
        produtos = no.get("produtos")
        if isinstance(produtos, list) and produto in produtos:
            return True
        # checa sub-estruturas conhecidas
        for chave in ("subcategorias", "grupos"):
            sub = no.get(chave)
            if isinstance(sub, dict):
                for sk, sn in sub.items():
                    if _buscar_produto_recursivo(sn, produto):
                        return True
        # checa quaisquer dict children
        for k, v in no.items():
            if k in ("produtos", "subcategorias", "grupos"):
                continue
            if isinstance(v, dict) and _buscar_produto_recursivo(v, produto):
                return True
    elif isinstance(no, list):
        # nó é lista de produtos
        return produto in no
    return False


def categorias_para_itens(itens):
    """
    Retorna lista ordenada de categorias de topo do CATALOGO que contêm ao menos
    um produto presente em 'itens' (itens é uma lista de nomes).
    Se nenhuma categoria for encontrada, retorna todas as categorias como fallback.
    """
    cats = []
    seen = set()
    for prod in itens:
        for cat_key, cat_node in catalogo.CATALOGO.items():
            if _buscar_produto_recursivo(cat_node, prod):
                if cat_key not in seen:
                    cats.append(cat_key)
                    seen.add(cat_key)
                break
    if not cats:
        return list(catalogo.CATALOGO.keys())
    return cats


def _obter_no_por_caminho(caminho):
    """
    Retorna o nó do CATALOGO correspondente ao caminho (lista de chaves).
    Se não encontrar, retorna None.
    """
    node = None
    if not caminho:
        # top-level: o "nó" é o catálogo inteiro (representado como dict de categorias)
        return None
    # Tentamos navegar: cada segmento pode residir em 'subcategorias', 'grupos' ou como chave direta
    node = catalogo.CATALOGO
    for seg in caminho:
        if not isinstance(node, dict):
            return None
        found = None
        # procurar em 'subcategorias' e 'grupos'
        for container in ("subcategorias", "grupos"):
            cont = node.get(container)
            if isinstance(cont, dict) and seg in cont:
                found = cont[seg]
                break
        # procurar como chave direta
        if found is None and seg in node:
            found = node[seg]
        if found is None:
            return None
        node = found
    return node


def opcoes_filtradas_para_itens(caminho, itens):
    """
    Retorna a lista de opções (subcategorias, grupos e/ou produtos) presentes no nó
    apontado por 'caminho' que contêm pelo menos um produto de 'itens'.
    - Se caminho == [] (top-level), retorna as categorias de topo filtradas.
    - Caso não haja correspondência de filtro, faz fallback para catalogo.obter_opcoes(caminho).
    """
    # top-level: reutilizar categorias_para_itens
    if not caminho:
        return categorias_para_itens(itens)

    node = _obter_no_por_caminho(caminho)
    if node is None:
        # não conseguimos navegar até o nó; fallback
        return catalogo.obter_opcoes(caminho)

    opts = []
    seen = set()

    # produtos diretamente no nó
    produtos = node.get("produtos")
    if isinstance(produtos, list):
        for p in produtos:
            if p in itens and p not in seen:
                opts.append(p)
                seen.add(p)

    # subcategorias e grupos
    for container in ("subcategorias", "grupos"):
        cont = node.get(container)
        if isinstance(cont, dict):
            for sk, sn in cont.items():
                # se algum produto da lista estiver dentro da sub-árvore
                if any(_buscar_produto_recursivo(sn, prod) for prod in itens):
                    if sk not in seen:
                        opts.append(sk)
                        seen.add(sk)

    # outros filhos dict (arquiteturas variadas)
    for k, v in node.items():
        if k in ("produtos", "subcategorias", "grupos"):
            continue
        if isinstance(v, dict):
            if any(_buscar_produto_recursivo(v, prod) for prod in itens):
                if k not in seen:
                    opts.append(k)
                    seen.add(k)

    if not opts:
        # fallback para mostrar tudo no nível atual
        return catalogo.obter_opcoes(caminho)

    return opts


async def voltar_para_origem(message: types.Message, state: FSMContext):
    """
    Retorna o usuário para o menu de onde ele veio, baseado em `menu_origin` no estado.
    - 'compras' -> retorna ao menu de compras (sai da seleção de listas)
    - 'cadastro' (padrão) -> retorna ao gerenciador de listas (kb_listas_menu)
    """
    data = await state.get_data()
    origin = data.get("menu_origin", "cadastro")
    dep_id, _ = await get_dep_from_state(state)

    if origin == "compras":
        # voltar para o menu de compras (preservando departamento)
        await limpar_estado_preservando_departamento(state)
        return await message.answer("🛒 Menu de Compras:", reply_markup=kb_menu())
    else:
        # origem cadastro/gerenciador -> voltar ao gerenciador de listas
        await state.set_state(ListaState.escolhendo_lista)
        await state.update_data(acao="iniciar_compra", menu_origin="compras")
        listas = await database.pegar_listas_disponiveis(dep_id) if dep_id else []
        return await message.answer("Selecione a lista para iniciar a compra:", reply_markup=kb_lista_escolha(listas))


# --- HANDLERS ---

# Finalizar: único comando que realmente finaliza/limpa tudo
@router.message(F.text == "🏁 Finalizar")
async def finalizar_fluxo(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Fluxo finalizado.", reply_markup=kb_menu())


# Handler para o módulo de COMPRAS — ao clicar em "📋 Minhas Listas" partimos direto para INICIAR COMPRA
@router.message(F.text == "📋 Minhas Listas")
async def listas_minhas_compras(message: types.Message, state: FSMContext):
    dep_id, _ = await get_dep_from_state(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento primeiro.")
    listas = await database.pegar_listas_disponiveis(dep_id)
    if not listas:
        return await message.answer("Não há listas. Crie uma lista primeiro!", reply_markup=kb_listas_menu(allow_iniciar=False))
    # marcar origem como compras
    await state.set_state(ListaState.escolhendo_lista)
    await state.update_data(acao="iniciar_compra", menu_origin="compras")
    await message.answer("Selecione a lista para iniciar a compra:", reply_markup=kb_lista_escolha(listas))


# Handler para o módulo de CADASTROS — ao clicar em "📋 Listas" abrimos o gerenciador sem botão "Iniciar Compra"
@router.message(F.text == "📋 Listas")
async def listas_cadastros_manager(message: types.Message, state: FSMContext):
    dep_id, _ = await get_dep_from_state(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento primeiro.")
    # marcar origem como cadastro (gerenciador)
    await state.set_state(ListaState.escolhendo_lista)
    await state.update_data(menu_origin="cadastro")
    await message.answer("Gerenciar Listas:", reply_markup=kb_listas_menu(allow_iniciar=False))


@router.message(F.text == "⬅️ Menu Principal")
async def back_main(message: types.Message, state: FSMContext):
    # volta ao menu principal, preservando departamento (se existia)
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
        return await message.answer("Envie /start e escolha o departamento primeiro.")
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
    # marcar origem como cadastro (adicionar itens é parte do gerenciador)
    await state.set_state(ListaState.escolhendo_lista)
    await state.update_data(acao="adicionar", menu_origin="cadastro")
    await message.answer("Selecione a lista:", reply_markup=kb_lista_escolha(listas))


@router.message(ListaState.escolhendo_lista)
async def list_chosen(message: types.Message, state: FSMContext):
    # "⬅️ Voltar" deve retornar ao menu de origem (não finalizar)
    if message.text == "⬅️ Voltar":
        return await voltar_para_origem(message, state)

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
        # preservar menu_origin existente (geralmente 'cadastro')
        # armazena também os itens da lista para filtragem dinâmica
        await state.update_data(caminho=[], lista_nome=lista_nome, lista_itens=itens)
        opts = opcoes_filtradas_para_itens([], itens)
        # mostrar categorias com botão Voltar (sempre)
        return await message.answer("Escolha a categoria:", reply_markup=kb_opcoes(opts, True))

    # caso iniciar compra
    itens = await database.pegar_itens_da_lista(lista_row["id"])
    if not itens:
        # se lista vazia, voltar para menu de origem (preservando fluxo)
        return await voltar_para_origem(message, state)
    await state.set_state(ListaState.compra_navegando)
    await state.update_data(itens_pendentes=itens, caminho=[])
    # mostrar apenas categorias que contêm os produtos da lista (top-level)
    categorias_filtradas = categorias_para_itens(itens)
    return await message.answer(f"Iniciando compra: {lista_nome}", reply_markup=kb_opcoes(categorias_filtradas, True))


@router.message(ListaState.navegando_catalogo)
async def nav_add(message: types.Message, state: FSMContext):
    data = await state.get_data()
    caminho = data.get("caminho", [])
    lista_itens = data.get("lista_itens", [])

    # "⬅️ Voltar": se em nível interno -> sobe um nível; se no topo -> volta para menu de origem
    if message.text == "⬅️ Voltar":
        if not caminho:
            return await voltar_para_origem(message, state)
        caminho.pop()
        await state.update_data(caminho=caminho)
        opts = opcoes_filtradas_para_itens(caminho, lista_itens)
        # sempre mostrar '⬅️ Voltar' nas categorias
        return await message.answer("Selecione:", reply_markup=kb_opcoes(opts, True))

    escolha = message.text.strip()
    tipo, chave = catalogo.identificar_escolha(caminho, escolha)

    if tipo == "categoria":
        caminho.append(chave)
        await state.update_data(caminho=caminho)
        opts = opcoes_filtradas_para_itens(caminho, lista_itens)
        await message.answer("Selecione:", reply_markup=kb_opcoes(opts, True))
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
        # atualizar lista_itens no estado e recomputar opções filtradas
        await state.update_data(lista_itens=itens_atualizados, caminho=caminho_atual, lista_nome=lista_nome)
        opts = opcoes_filtradas_para_itens(caminho_atual, itens_atualizados)
        await state.set_state(ListaState.navegando_catalogo)
        return await message.answer("Deseja adicionar mais itens? Selecione:", reply_markup=kb_opcoes(opts, True))

    await message.answer("Escolha inválida.")


# --- FLUXO: iniciar compra a partir da lista (itens_pendentes) ---
@router.message(ListaState.compra_navegando)
async def compra_navegar(message: types.Message, state: FSMContext):
    # "⬅️ Voltar" deve retornar para menu de origem (ex.: seleção de listas para iniciar compra)
    if message.text == "⬅️ Voltar":
        return await voltar_para_origem(message, state)

    data = await state.get_data()
    caminho = data.get("caminho", [])
    itens_pendentes = data.get("itens_pendentes", [])

    if message.text == "❌ Cancelar":
        # cancelar volta para menu de origem
        return await voltar_para_origem(message, state)

    escolha = message.text.strip()
    tipo, chave = catalogo.identificar_escolha(caminho, escolha)
    if tipo == "categoria":
        caminho.append(chave)
        await state.update_data(caminho=caminho)
        # mostrar apenas opções filtradas com base nos itens_pendentes
        opts = opcoes_filtradas_para_itens(caminho, itens_pendentes)
        await message.answer("Selecione:", reply_markup=kb_opcoes(opts, True))
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
            # mostrar apenas categorias relevantes aos itens pendentes
            opts = categorias_para_itens(itens_pendentes)
            await message.answer(f"✅ {catalogo.formatar(produto)} adicionado! Próximo item:", reply_markup=kb_opcoes(opts, True))
        else:
            # quando todos adicionados, voltar ao menu de origem (provavelmente seleção de listas)
            return await voltar_para_origem(message, state)
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
    # marcar origem como cadastro (remoção faz parte do gerenciador)
    await state.set_state(ListaState.escolhendo_lista_remover)
    await state.update_data(menu_origin="cadastro")
    await message.answer("Selecione a lista:", reply_markup=kb_lista_escolha(listas))


@router.message(ListaState.escolhendo_lista_remover)
async def remover_item_lista_handler(message: types.Message, state: FSMContext):
    dep_id, _ = await get_dep_from_state(state)
    # "⬅️ Voltar" retorna ao menu de origem
    if message.text == "⬅️ Voltar":
        return await voltar_para_origem(message, state)

    lista_row = await database.buscar_lista_por_nome(dep_id, message.text)
    if not lista_row:
        await state.clear()
        return await message.answer("Lista não encontrada.", reply_markup=kb_listas_menu())

    itens = await database.pegar_itens_da_lista(lista_row["id"])
    if not itens:
        # permanece no fluxo de escolha de listas para remover (mas mantendo origem)
        listas = await database.pegar_listas_disponiveis(dep_id)
        await state.set_state(ListaState.escolhendo_lista_remover)
        return await message.answer("Lista vazia. Selecione outra lista:", reply_markup=kb_lista_escolha(listas))

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

    # "⬅️ Voltar": voltar para seleção de listas para remover (ou menu de origem)
    if message.text == "⬅️ Voltar":
        return await voltar_para_origem(message, state)

    itens_atuais = await database.pegar_itens_da_lista(lista_id)
    item_raw = encontrar_item_raw_por_label(itens_atuais, message.text)

    if not item_raw:
        return await message.answer("Item não encontrado. Selecione um item válido.")

    # remover no banco
    await database.remover_item_lista(lista_id, item_raw)

    # reconsultar itens restantes depois da remoção
    itens_restantes = await database.pegar_itens_da_lista(lista_id)

    if not itens_restantes:
        # quando a lista ficou vazia, voltar para menu de origem (escolha de listas)
        return await voltar_para_origem(message, state)

    btns = [[KeyboardButton(text=catalogo.formatar(i))] for i in itens_restantes]
    btns.append([KeyboardButton(text="⬅️ Voltar")])
    kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

    await state.set_state(ListaState.removendo_item)
    await state.update_data(lista_id=lista_id, lista_nome=lista_nome, departamento_id=dep_id)

    return await message.answer(
        f"✅ {catalogo.formatar(item_raw)} removido.\n\nSelecione outro item para remover:",
        reply_markup=kb
    )