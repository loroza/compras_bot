from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
import catalogo
import database

router = Router()


class ListaState(StatesGroup):
    criando_tipo = State()
    criando_nome = State()
    escolhendo_lista = State()
    escolhendo_lista_remover = State()
    navegando_catalogo = State()
    compra_navegando = State()
    compra_quantidade = State()
    compra_valor = State()
    removendo_navegando = State()  # navegação para remover itens


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
    rows = [
        [KeyboardButton(text="➕ Nova Lista")],
        [KeyboardButton(text="📝 Adicionar Itens")],
    ]
    if allow_iniciar:
        rows[-1].append(KeyboardButton(text="🚀 Iniciar Compra"))

    rows.append([KeyboardButton(text="🗑️ Remover Item"), KeyboardButton(text="⬅️ Menu Principal")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def kb_opcoes(lista, voltar: bool = True):
    btns = [[KeyboardButton(text=catalogo.formatar(opt))] for opt in lista]
    if voltar:
        btns.append([KeyboardButton(text="⬅️ Voltar")])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)


def kb_lista_escolha(listas):
    btns = [[KeyboardButton(text=l["nome"])] for l in listas]
    btns.append([KeyboardButton(text="⬅️ Voltar")])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)


def kb_tipo_lista():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Avulsa"), KeyboardButton(text="Fixa")],
            [KeyboardButton(text="⬅️ Voltar")]
        ],
        resize_keyboard=True,
    )


# --- HELPERS ---
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
    return catalogo.formatar_extrato(itens)


def encontrar_item_raw_por_label(itens: list, label: str):
    for item in itens:
        if catalogo.formatar(item) == label:
            return item
    return None


# --- CATALOG NAV HELPERS ---
def _buscar_produto_recursivo(no, produto):
    if isinstance(no, dict):
        produtos = no.get("produtos")
        if isinstance(produtos, list) and produto in produtos:
            return True
        for chave in ("subcategorias", "grupos"):
            sub = no.get(chave)
            if isinstance(sub, dict):
                for sk, sn in sub.items():
                    if _buscar_produto_recursivo(sn, produto):
                        return True
        for k, v in no.items():
            if k in ("produtos", "subcategorias", "grupos"):
                continue
            if isinstance(v, dict) and _buscar_produto_recursivo(v, produto):
                return True
    elif isinstance(no, list):
        return produto in no
    return False


def categorias_para_itens(itens):
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
    if not caminho:
        return None
    node = catalogo.CATALOGO
    for seg in caminho:
        if not isinstance(node, dict):
            return None
        found = None
        for container in ("subcategorias", "grupos"):
            cont = node.get(container)
            if isinstance(cont, dict) and seg in cont:
                found = cont[seg]
                break
        if found is None and seg in node:
            found = node[seg]
        if found is None:
            return None
        node = found
    return node


def opcoes_filtradas_para_itens(caminho, itens):
    if not caminho:
        return categorias_para_itens(itens)

    node = _obter_no_por_caminho(caminho)
    if node is None:
        return catalogo.obter_opcoes(caminho)

    opts = []
    seen = set()

    produtos = node.get("produtos")
    if isinstance(produtos, list):
        for p in produtos:
            if p in itens and p not in seen:
                opts.append(p)
                seen.add(p)

    for container in ("subcategorias", "grupos"):
        cont = node.get(container)
        if isinstance(cont, dict):
            for sk, sn in cont.items():
                if any(_buscar_produto_recursivo(sn, prod) for prod in itens):
                    if sk not in seen:
                        opts.append(sk)
                        seen.add(sk)

    for k, v in node.items():
        if k in ("produtos", "subcategorias", "grupos"):
            continue
        if isinstance(v, dict):
            if any(_buscar_produto_recursivo(v, prod) for prod in itens):
                if k not in seen:
                    opts.append(k)
                    seen.add(k)

    if not opts:
        return catalogo.obter_opcoes(caminho)

    return opts


async def voltar_para_origem(message: types.Message, state: FSMContext):
    data = await state.get_data()
    origin = data.get("menu_origin", "cadastro")
    dep_id, _ = await get_dep_from_state(state)

    if origin == "compras":
        await limpar_estado_preservando_departamento(state)
        kb_compras = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🛒 Compra Avulsa"), KeyboardButton(text="📋 Minhas Listas")],
                [KeyboardButton(text="📦 Ver Carrinho")],
                [KeyboardButton(text="⬅️ Menu Principal")],
            ],
            resize_keyboard=True,
        )
        return await message.answer("🛒 Menu de Compras:", reply_markup=kb_compras)
    else:
        # volta para gestão de listas (cadastros)
        await state.set_state(ListaState.escolhendo_lista)
        await state.update_data(acao="iniciar_compra", menu_origin="compras")
        listas = await database.pegar_listas_disponiveis(dep_id) if dep_id else []
        return await message.answer("Selecione a lista para iniciar a compra:", reply_markup=kb_lista_escolha(listas))


# --- HANDLERS ---

@router.message(F.text == "🏁 Finalizar")
async def finalizar_fluxo(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Fluxo finalizado.", reply_markup=kb_menu())


@router.message(F.text == "📋 Minhas Listas")
async def listas_minhas_compras(message: types.Message, state: FSMContext):
    dep_id, _ = await get_dep_from_state(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha um departamento primeiro.")
    listas = await database.pegar_listas_disponiveis(dep_id)
    if not listas:
        return await message.answer("Não há listas. Crie uma lista primeiro!", reply_markup=kb_listas_menu(allow_iniciar=False))
    await state.set_state(ListaState.escolhendo_lista)
    await state.update_data(acao="iniciar_compra", menu_origin="compras")
    await message.answer("Selecione a lista para iniciar a compra:", reply_markup=kb_lista_escolha(listas))


@router.message(F.text == "📋 Listas")
async def listas_cadastros_manager(message: types.Message, state: FSMContext):
    dep_id, _ = await get_dep_from_state(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha o departamento primeiro.")
    await state.set_state(ListaState.escolhendo_lista)
    await state.update_data(menu_origin="cadastro")
    await message.answer("Gerenciar Listas:", reply_markup=kb_listas_menu(allow_iniciar=False))


@router.message(F.text == "⬅️ Menu Principal")
async def back_main(message: types.Message, state: FSMContext):
    await limpar_estado_preservando_departamento(state)
    await message.answer("Menu Principal:", reply_markup=kb_menu())


@router.message(F.text == "➕ Nova Lista")
async def new_list(message: types.Message, state: FSMContext):
    dep_id, _ = await get_dep_from_state(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha o departamento primeiro.")
    await state.set_state(ListaState.criando_tipo)
    await message.answer("Qual o tipo da lista?\nEscolha 'Avulsa' (lista comum) ou 'Fixa' (lista reutilizável).", reply_markup=kb_tipo_lista())


@router.message(ListaState.criando_tipo)
async def choose_list_type(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Voltar":
        await state.set_state(ListaState.escolhendo_lista)
        await state.update_data(menu_origin="cadastro")
        return await message.answer("Gerenciar Listas:", reply_markup=kb_listas_menu(allow_iniciar=False))

    text = message.text.strip().lower()
    if text not in ("avulsa", "fixa"):
        return await message.answer("Por favor escolha 'Avulsa' ou 'Fixa' (ou clique '⬅️ Voltar').", reply_markup=kb_tipo_lista())

    lista_tipo = "avulsa" if text == "avulsa" else "fixa"
    await state.update_data(lista_tipo=lista_tipo)
    await state.set_state(ListaState.criando_nome)
    await message.answer("Digite o nome da lista:", reply_markup=ReplyKeyboardRemove())


@router.message(ListaState.criando_nome)
async def save_list(message: types.Message, state: FSMContext):
    dep_id, _ = await get_dep_from_state(state)
    if not dep_id:
        await state.clear()
        return await message.answer("Envie /start e escolha o departamento primeiro.")

    lista_nome = message.text.strip()
    data = await state.get_data()
    lista_tipo = data.get("lista_tipo", "avulsa")

    sucesso = await database.criar_lista(dep_id, lista_nome, lista_tipo)

    await limpar_estado_preservando_departamento(state)
    await state.set_state(ListaState.escolhendo_lista)
    await state.update_data(menu_origin="cadastro")

    if sucesso:
        await message.answer(f"✅ Lista *{lista_nome}* criada ({lista_tipo}).", parse_mode="Markdown", reply_markup=kb_listas_menu())
    else:
        await message.answer("❌ Não foi possível criar a lista (nome já existe?).", reply_markup=kb_listas_menu())


@router.message(F.text == "📝 Adicionar Itens")
async def add_item_start(message: types.Message, state: FSMContext):
    dep_id, _ = await get_dep_from_state(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha o departamento primeiro.")
    listas = await database.pegar_listas_disponiveis(dep_id)
    if not listas:
        return await message.answer("Crie uma lista primeiro!", reply_markup=kb_listas_menu())
    await state.set_state(ListaState.escolhendo_lista)
    await state.update_data(acao="adicionar", menu_origin="cadastro")
    await message.answer("Selecione a lista:", reply_markup=kb_lista_escolha(listas))


@router.message(ListaState.escolhendo_lista)
async def list_chosen(message: types.Message, state: FSMContext):
    # Handler dedicado para seleção de listas nos fluxos de cadastro/compras (não-remocao)
    if message.text == "⬅️ Voltar":
        return await voltar_para_origem(message, state)

    data = await state.get_data()
    dep_id, _ = await get_dep_from_state(state)
    if not dep_id:
        await state.clear()
        return await message.answer("Envie /start e escolha o departamento primeiro.")

    lista_nome = message.text.strip()
    lista_row = await database.buscar_lista_por_nome(dep_id, lista_nome)

    if not lista_row:
        listas_disponiveis = await database.pegar_listas_disponiveis(dep_id)
        text_norm = lista_nome.lower()
        for l in listas_disponiveis:
            if l.get("nome", "").strip().lower() == text_norm:
                lista_row = l
                break

    if not lista_row:
        listas = await database.pegar_listas_disponiveis(dep_id)
        if not listas:
            return await message.answer("Lista não encontrada e não há listas disponíveis.", reply_markup=kb_listas_menu(allow_iniciar=False))
        await state.set_state(ListaState.escolhendo_lista)
        menu_origin = data.get("menu_origin", "cadastro")
        await state.update_data(menu_origin=menu_origin)
        return await message.answer("Lista não encontrada. Selecione uma das listas abaixo:", reply_markup=kb_lista_escolha(listas))

    acao = data.get("acao")

    # ADICIONAR ITENS (cadastro)
    if acao == "adicionar":
        itens = await database.pegar_itens_da_lista(lista_row["id"])
        extrato = montar_extrato_texto(itens)
        await message.answer(f"Extrato atual da lista *{lista_row.get('nome')}*:\n\n{extrato}", parse_mode="Markdown")
        await state.set_state(ListaState.navegando_catalogo)
        await state.update_data(caminho=[], lista_nome=lista_row.get("nome"), lista_itens=itens, acao="adicionar")
        opts = catalogo.obter_opcoes([])
        return await message.answer("Escolha a categoria:", reply_markup=kb_opcoes(opts, True))

    # INICIAR COMPRA A PARTIR DA LISTA
    itens = await database.pegar_itens_da_lista(lista_row["id"])
    if not itens:
        await database.deletar_lista(lista_row["id"])
        return await message.answer("A lista estava vazia e foi excluída automaticamente.", reply_markup=kb_menu())

    lista_id = lista_row["id"]
    lista_tipo = lista_row.get("tipo", "avulsa")

    await state.set_state(ListaState.compra_navegando)
    await state.update_data(itens_pendentes=itens, caminho=[], lista_id=lista_id, lista_tipo=lista_tipo)
    categorias_filtradas = categorias_para_itens(itens)
    return await message.answer(f"Iniciando compra: {lista_row.get('nome')}", reply_markup=kb_opcoes(categorias_filtradas, True))


# Handler DEDICADO para seleção de lista no fluxo de REMOÇÃO
@router.message(ListaState.escolhendo_lista_remover)
async def list_chosen_remover(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Voltar":
        # voltar para menu de cadastros
        await state.set_state(ListaState.escolhendo_lista)
        await state.update_data(menu_origin="cadastro")
        return await message.answer("Gerenciar Listas:", reply_markup=kb_listas_menu(allow_iniciar=False))

    dep_id, _ = await get_dep_from_state(state)
    if not dep_id:
        await state.clear()
        return await message.answer("Envie /start e escolha o departamento primeiro.")

    lista_nome = message.text.strip()
    lista_row = await database.buscar_lista_por_nome(dep_id, lista_nome)

    if not lista_row:
        listas = await database.pegar_listas_disponiveis(dep_id)
        return await message.answer("Lista não encontrada. Selecione uma das listas abaixo:", reply_markup=kb_lista_escolha(listas))

    itens = await database.pegar_itens_da_lista(lista_row["id"])
    if not itens:
        await database.deletar_lista(lista_row["id"])
        listas = await database.pegar_listas_disponiveis(dep_id)
        if not listas:
            await state.clear()
            return await message.answer(
                "A lista estava vazia e foi excluída automaticamente. Não há mais listas.",
                reply_markup=kb_listas_menu(allow_iniciar=False),
            )
        return await message.answer("A lista estava vazia e foi excluída automaticamente. Selecione outra lista:", reply_markup=kb_lista_escolha(listas))

    # iniciar navegação de remoção
    await state.set_state(ListaState.removendo_navegando)
    await state.update_data(
        lista_id=lista_row["id"],
        lista_nome=lista_row["nome"],
        lista_itens=itens,
        caminho=[],
        acao="remover_item",
        menu_origin="cadastro",
    )
    top_cats = categorias_para_itens(itens)
    return await message.answer(f"Remover item da lista *{lista_row['nome']}*\nEscolha a categoria:", parse_mode="Markdown", reply_markup=kb_opcoes(top_cats, True))


# NAVEGAÇÃO PARA ADICIONAR (mantive igual)
@router.message(ListaState.navegando_catalogo)
async def nav_add(message: types.Message, state: FSMContext):
    data = await state.get_data()
    caminho = data.get("caminho", [])
    lista_itens = data.get("lista_itens", [])

    if message.text == "⬅️ Voltar":
        if not caminho:
            return await voltar_para_origem(message, state)
        caminho.pop()
        await state.update_data(caminho=caminho)
        acao = data.get("acao")
        menu_origin = data.get("menu_origin", "")
        if acao == "adicionar" or menu_origin == "cadastro":
            opts = catalogo.obter_opcoes(caminho)
        else:
            opts = opcoes_filtradas_para_itens(caminho, lista_itens)
        return await message.answer("Selecione:", reply_markup=kb_opcoes(opts, True))

    escolha = message.text.strip()
    tipo, chave = catalogo.identificar_escolha(caminho, escolha)

    if tipo == "categoria":
        caminho.append(chave)
        await state.update_data(caminho=caminho)
        acao = data.get("acao")
        menu_origin = data.get("menu_origin", "")
        if acao == "adicionar" or menu_origin == "cadastro":
            opts = catalogo.obter_opcoes(caminho)
        else:
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
        await database.adicionar_item_lista(lista_row["id"], chave)

        itens_atualizados = await database.pegar_itens_da_lista(lista_row["id"])
        extrato = montar_extrato_texto(itens_atualizados)
        await message.answer(f"✅ {catalogo.formatar(chave)} adicionado à lista *{lista_nome}*!\n\nExtrato atualizado:\n\n{extrato}", parse_mode="Markdown")

        caminho_atual = data.get("caminho", [])
        await state.update_data(lista_itens=itens_atualizados, caminho=caminho_atual, lista_nome=lista_nome)
        acao = data.get("acao")
        menu_origin = data.get("menu_origin", "")
        if acao == "adicionar" or menu_origin == "cadastro":
            opts = catalogo.obter_opcoes(caminho_atual)
        else:
            opts = opcoes_filtradas_para_itens(caminho_atual, itens_atualizados)
        await state.set_state(ListaState.navegando_catalogo)
        return await message.answer("Deseja adicionar mais itens? Selecione:", reply_markup=kb_opcoes(opts, True))

    await message.answer("Escolha inválida.")


# NAVEGAÇÃO PARA REMOVER: Categoria -> Subcategoria -> Item -> remover
@router.message(ListaState.removendo_navegando)
async def nav_remove(message: types.Message, state: FSMContext):
    data = await state.get_data()
    caminho = data.get("caminho", [])
    lista_itens = data.get("lista_itens", [])

    # voltar: se no topo, volta à seleção de listas para remover; se dentro, sobe nível
    if message.text == "⬅️ Voltar":
        if not caminho:
            await state.set_state(ListaState.escolhendo_lista_remover)
            dep_id, _ = await get_dep_from_state(state)
            listas = await database.pegar_listas_disponiveis(dep_id)
            return await message.answer("Selecione a lista para remover itens:", reply_markup=kb_lista_escolha(listas))
        caminho.pop()
        await state.update_data(caminho=caminho)
        opts = opcoes_filtradas_para_itens(caminho, lista_itens)
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
        produto = chave
        lista_id = data.get("lista_id")
        lista_nome = data.get("lista_nome")
        if not lista_id:
            return await message.answer("Erro: lista não encontrada no estado.")

        # realiza remoção no DB
        await database.remover_item_lista(lista_id, produto)

        # reconsulta itens restantes
        itens_restantes = await database.pegar_itens_da_lista(lista_id)

        if not itens_restantes:
            deleted = await database.deletar_lista(lista_id)
            if deleted:
                await state.clear()
                return await message.answer(f"✅ {catalogo.formatar(produto)} removido. A lista *{lista_nome}* ficou vazia e foi excluída.", parse_mode="Markdown", reply_markup=kb_menu())
            else:
                await state.clear()
                return await message.answer(f"✅ {catalogo.formatar(produto)} removido. A lista ficou vazia, mas não foi possível removê-la automaticamente.", parse_mode="Markdown", reply_markup=kb_menu())

        # atualiza estado e permanece no fluxo de remoção para remover mais itens
        await state.update_data(lista_itens=itens_restantes)
        opts = opcoes_filtradas_para_itens(caminho, itens_restantes)
        await state.set_state(ListaState.removendo_navegando)
        await message.answer(f"✅ {catalogo.formatar(produto)} removido da lista *{lista_nome}*.", parse_mode="Markdown")
        return await message.answer("Selecione o próximo item para remover ou volte:", reply_markup=kb_opcoes(opts, True))

    await message.answer("Escolha inválida.")


@router.message(ListaState.compra_navegando)
async def compra_navegar(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Voltar":
        return await voltar_para_origem(message, state)

    data = await state.get_data()
    caminho = data.get("caminho", [])
    itens_pendentes = data.get("itens_pendentes", [])

    if message.text == "❌ Cancelar":
        return await voltar_para_origem(message, state)

    escolha = message.text.strip()
    tipo, chave = catalogo.identificar_escolha(caminho, escolha)
    if tipo == "categoria":
        caminho.append(chave)
        await state.update_data(caminho=caminho)
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
            return await message.answer("Envie /start e escolha o departamento primeiro.")
        lista_id = data.get("lista_id")

        await database.adicionar_ao_carrinho(message.from_user.id, dep_id, produto, qtd, valor)

        if lista_id:
            await database.remover_item_lista(lista_id, produto)

        itens_pendentes = data.get("itens_pendentes", [])
        if produto in itens_pendentes:
            itens_pendentes.remove(produto)

        itens_restantes_db = []
        if lista_id:
            itens_restantes_db = await database.pegar_itens_da_lista(lista_id)

        extrato_texto = None
        try:
            if lista_id:
                extrato_texto = montar_extrato_texto(itens_restantes_db)
                msg_principal = f"✅ {catalogo.formatar(produto)} adicionado ao carrinho!\n\nExtrato atualizado da lista:\n\n{extrato_texto}"
            else:
                pegar_carrinho = getattr(database, "pegar_carrinho", None)
                if pegar_carrinho:
                    carrinho = await database.pegar_carrinho(message.from_user.id, dep_id)
                    extrato_texto = montar_extrato_texto(carrinho)
                    msg_principal = f"✅ {catalogo.formatar(produto)} adicionado ao carrinho!\n\nExtrato do carrinho:\n\n{extrato_texto}"
                else:
                    msg_principal = f"✅ {catalogo.formatar(produto)} adicionado ao carrinho!"
        except Exception:
            msg_principal = f"✅ {catalogo.formatar(produto)} adicionado ao carrinho!"

        await state.update_data(itens_pendentes=itens_pendentes)

        if itens_pendentes:
            await state.set_state(ListaState.compra_navegando)
            await state.update_data(caminho=[])
            opts = categorias_para_itens(itens_pendentes)
            await message.answer(msg_principal, reply_markup=ReplyKeyboardRemove())
            await message.answer("Próximo item:", reply_markup=kb_opcoes(opts, True))
        else:
            if lista_id and not itens_restantes_db:
                deleted = await database.deletar_lista(lista_id)
                if deleted:
                    await message.answer(msg_principal)
                    await message.answer("✅ Todos os itens comprados — a lista foi removida automaticamente.")
                else:
                    await message.answer(msg_principal)
                    await message.answer("✅ Compra finalizada. (Não foi possível remover automaticamente a lista.)")
            else:
                await message.answer(msg_principal)
                await message.answer("✅ Compra finalizada.")
            return await voltar_para_origem(message, state)
    except Exception:
        await message.answer("Valor inválido.")


@router.message(F.text == "🗑️ Remover Item")
async def remover_item_start(message: types.Message, state: FSMContext):
    dep_id, _ = await get_dep_from_state(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha o departamento primeiro.")

    # limpa estado mantendo apenas dados do departamento para evitar restos de fluxos anteriores
    await limpar_estado_preservando_departamento(state)

    listas = await database.pegar_listas_disponiveis(dep_id)
    if not listas:
        return await message.answer("Não há listas para remover itens.", reply_markup=kb_listas_menu())

    # setar estado dedicado para seleção de lista a ser removida
    await state.set_state(ListaState.escolhendo_lista_remover)
    await state.update_data(menu_origin="cadastro")

    await message.answer(
        "Selecione a lista para remover itens (em seguida você escolherá categoria → subcategoria → item):",
        reply_markup=kb_lista_escolha(listas),
    )