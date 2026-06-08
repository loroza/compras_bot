# listas.py (versão ajustada para exibir extrato do carrinho quando necessário)
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
import catalogo
import database

import os
import time
import json

# DEBUG: instrumentação para identificar handlers/instâncias que tratam cada mensagem
print(f"[STARTUP] listas.py loaded PID={os.getpid()} ts={time.time():.3f}")


async def _log_handler_entry(handler_name: str, message, state):
    """
    Chamar esta função como primeira linha de cada handler que queremos
    instrumentar. Não altera comportamento, só imprime estado/usuario/texto.
    """
    try:
        state_name = await state.get_state()
        state_data = await state.get_data()
    except Exception as e:
        state_name = f"ERR:{e}"
        state_data = {}
    user_id = getattr(getattr(message, "from_user", None), "id", None)
    text = getattr(message, "text", None)
    try:
        data_json = json.dumps(state_data, default=str, ensure_ascii=False)
    except Exception:
        data_json = str(state_data)
    print(
        f"[HANDLER] PID={os.getpid()} handler={handler_name} ts={time.time():.3f} "
        f"user={user_id} text={text!r} state={state_name} data={data_json}"
    )


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
    finalizando_opcao = State()  # novo estado: escolher entre finalizar compra / finalizar lista


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


# --- HELPERS LOCAIS: montar extrato do carrinho (similar ao main.montar_extrato_carrinho)
def montar_extrato_carrinho_local(itens):
    if not itens:
        return "Carrinho vazio."
    lines = []
    total = 0.0
    # agrupa por item_name
    agg = {}
    for r in itens:
        try:
            nome = r["item_nome"]
            qtd = float(r["quantidade"] or 0)
            valor = float(r["valor_unitario"] or 0)
        except Exception:
            nome = r[1]
            qtd = float(r[2] or 0)
            valor = float(r[3] or 0)
        if nome in agg:
            agg[nome]["qtd"] += qtd
        else:
            agg[nome] = {"qtd": qtd, "valor": valor}
    for nome, v in agg.items():
        subtotal = v["qtd"] * v["valor"]
        total += subtotal
        lines.append(f"• {catalogo.formatar(nome)}: {v['qtd']:.3f}x R${v['valor']:.2f} = R${subtotal:.2f}")
    lines.append(f"\nValor Total do Carrinho: R${total:.2f}")
    return "\n".join(lines)


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


# helper: coleta todos os produtos definidos no catálogo (chaves "raw")
def _coletar_todos_produtos():
    produtos = set()

    def _rec(no):
        if isinstance(no, dict):
            p = no.get("produtos")
            if isinstance(p, list):
                for it in p:
                    produtos.add(it)
            for k, v in no.items():
                if isinstance(v, dict):
                    _rec(v)
                elif isinstance(v, list):
                    for elem in v:
                        if isinstance(elem, dict):
                            _rec(elem)
        elif isinstance(no, list):
            for elem in no:
                if isinstance(elem, dict):
                    _rec(elem)

    _rec(catalogo.CATALOGO)
    return produtos


def opcoes_filtradas_para_itens(caminho, itens):
    """
    Retorna opções (categorias/subcategorias/produtos) filtradas
    apenas para os produtos que estão na lista `itens`.
    """
    # normaliza itens vindos do banco para chaves raw do catálogo
    all_products = _coletar_todos_produtos()
    # mapa label_formatada.lower() -> raw
    formatted_map = {catalogo.formatar(p).lower(): p for p in all_products}

    raw_items = set()
    for it in itens:
        if it in all_products:
            raw_items.add(it)
            continue
        key = str(it).strip()
        low = key.lower()
        if low in formatted_map:
            raw_items.add(formatted_map[low])
            continue
        # tentativa extra: correspondência por igualdade simples ignorando case
        for fm_label, raw in formatted_map.items():
            if fm_label == low:
                raw_items.add(raw)
                break

    # se raw_items estiver vazio, manter comportamento padrão
    if not caminho:
        # categorias que contêm algum produto da lista
        cats = []
        seen = set()
        for prod in raw_items:
            for cat_key, cat_node in catalogo.CATALOGO.items():
                if _buscar_produto_recursivo(cat_node, prod):
                    if cat_key not in seen:
                        cats.append(cat_key)
                        seen.add(cat_key)
                    break
        if not cats:
            return list(catalogo.CATALOGO.keys())
        return cats

    node = _obter_no_por_caminho(caminho)
    if node is None:
        return catalogo.obter_opcoes(caminho)

    opts = []
    seen = set()

    produtos = node.get("produtos")
    if isinstance(produtos, list):
        for p in produtos:
            if p in raw_items and p not in seen:
                opts.append(p)
                seen.add(p)

    for container in ("subcategorias", "grupos"):
        cont = node.get(container)
        if isinstance(cont, dict):
            for sk, sn in cont.items():
                # se algum produto raw da lista existir recursivamente neste subnó
                if any(_buscar_produto_recursivo(sn, prod) for prod in raw_items):
                    if sk not in seen:
                        opts.append(sk)
                        seen.add(sk)

    for k, v in node.items():
        if k in ("produtos", "subcategorias", "grupos"):
            continue
        if isinstance(v, dict):
            if any(_buscar_produto_recursivo(v, prod) for prod in raw_items):
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


# Função faltante: inicia o fluxo de remoção (corrige NameError)
async def remover_item_start(message: types.Message, state: FSMContext):
    dep_id, _ = await get_dep_from_state(state)
    if not dep_id:
        return await message.answer("Envie /start e escolha o departamento primeiro.")
    listas = await database.pegar_listas_disponiveis(dep_id)
    if not listas:
        return await message.answer("Não há listas.", reply_markup=kb_listas_menu(allow_iniciar=False))
    await state.set_state(ListaState.escolhendo_lista_remover)
    await state.update_data(menu_origin="cadastro", acao="remover")
    return await message.answer("Selecione a lista para remover itens:", reply_markup=kb_lista_escolha(listas))


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
        return await message.answer("Envie /start e escolha um departamento primeiro.")
    await state.set_state(ListaState.escolhendo_lista)
    await state.update_data(menu_origin="cadastro")
    await message.answer("Gerenciar Listas:", reply_markup=kb_listas_menu(allow_iniciar=False))


@router.message(F.text == "⬅️ Menu Principal")
async def back_main(message: types.Message, state: FSMContext):
    """
    Volta explicitamente para o menu principal (mostrando o mesmo teclado do main.py),
    preservando o departamento.
    """
    await limpar_estado_preservando_departamento(state)
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛒 Compras"), KeyboardButton(text="📲 Cadastros")],
            [KeyboardButton(text="📜 Histórico"), KeyboardButton(text="🔄 Trocar Departamento")],
        ],
        resize_keyboard=True,
    )
    await message.answer("Menu principal:", reply_markup=kb)


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
    # DEBUG entry
    await _log_handler_entry("list_chosen", message, state)

    # Se o usuário clicou no botão "Remover Item" enquanto está no estado escolhendo_lista,
    # delegamos para o handler que inicia o fluxo de remoção.
    if message.text == "🗑️ Remover Item":
        return await remover_item_start(message, state)

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

        # reconsulta listas disponíveis e redireciona para o menu de listas (cadastro)
        listas = await database.pegar_listas_disponiveis(dep_id)
        if not listas:
            # não há mais listas: limpa estado e mostra menu de listas em modo cadastro
            await state.clear()
            return await message.answer(
                "A lista estava vazia e foi excluída automaticamente. Não há mais listas.",
                reply_markup=kb_listas_menu(allow_iniciar=False),
            )

        # há outras listas: coloca usuário em escolhendo_lista para gerenciar
        await state.set_state(ListaState.escolhendo_lista)
        await state.update_data(menu_origin="cadastro")
        return await message.answer(
            "A lista estava vazia e foi excluída automaticamente. Selecione outra lista:",
            reply_markup=kb_lista_escolha(listas),
        )

    lista_id = lista_row["id"]
    lista_tipo = lista_row.get("tipo", "avulsa")

    await state.set_state(ListaState.compra_navegando)
    # itens_pendentes armazena a cópia dos itens para esta sessão (assim, lista fixa não é alterada no DB)
    await state.update_data(itens_pendentes=itens, caminho=[], lista_id=lista_id, lista_tipo=lista_tipo, lista_nome=lista_row.get("nome"))
    categorias_filtradas = categorias_para_itens(itens)
    return await message.answer(f"Iniciando compra: {lista_row.get('nome')}", reply_markup=kb_opcoes(categorias_filtradas, True))


# Handler DEDICADO para seleção de lista no fluxo de REMOÇÃO
@router.message(ListaState.escolhendo_lista_remover)
async def list_chosen_remover(message: types.Message, state: FSMContext):
    # DEBUG entry
    await _log_handler_entry("list_chosen_remover", message, state)

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
    # DEBUG entry
    await _log_handler_entry("nav_add", message, state)

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
    # DEBUG entry
    await _log_handler_entry("nav_remove", message, state)

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

            # reconsulta listas disponíveis
            dep_id, _ = await get_dep_from_state(state)
            listas = await database.pegar_listas_disponiveis(dep_id) if dep_id else []

            if deleted:
                if not listas:
                    # nenhuma lista restante: limpa estado e mostra menu de listas (cadastro)
                    await state.clear()
                    return await message.answer(
                        f"✅ {catalogo.formatar(produto)} removido. A lista *{lista_nome}* ficou vazia e foi excluída.",
                        parse_mode="Markdown",
                        reply_markup=kb_listas_menu(allow_iniciar=False),
                    )

                # há outras listas: volta para escolhendo_lista no fluxo de cadastro
                await state.set_state(ListaState.escolhendo_lista)
                await state.update_data(menu_origin="cadastro")
                return await message.answer(
                    f"✅ {catalogo.formatar(produto)} removido. A lista *{lista_nome}* ficou vazia e foi excluída. Selecione outra lista:",
                    parse_mode="Markdown",
                    reply_markup=kb_lista_escolha(listas),
                )
            else:
                # falha ao deletar: limpa estado e mostre menu de listas para evitar loops
                await state.clear()
                return await message.answer(
                    f"✅ {catalogo.formatar(produto)} removido. A lista ficou vazia, mas não foi possível removê-la automaticamente.",
                    parse_mode="Markdown",
                    reply_markup=kb_listas_menu(allow_iniciar=False),
                )

        # atualiza estado e permanece no fluxo de remoção para remover mais itens
        await state.update_data(lista_itens=itens_restantes)
        opts = opcoes_filtradas_para_itens(caminho, itens_restantes)
        await state.set_state(ListaState.removendo_navegando)
        await message.answer(f"✅ {catalogo.formatar(produto)} removido da lista *{lista_nome}*.", parse_mode="Markdown")
        return await message.answer("Selecione o próximo item para remover ou volte:", reply_markup=kb_opcoes(opts, True))

    await message.answer("Escolha inválida.")


@router.message(ListaState.compra_navegando)
async def compra_navegar(message: types.Message, state: FSMContext):
    # DEBUG entry
    await _log_handler_entry("compra_navegar", message, state)

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
    except Exception:
        await message.answer("Valor inválido.")
        return

    data = await state.get_data()
    produto = data.get("produto")
    qtd = data.get("qtd")
    dep_id, _ = await get_dep_from_state(state)
    if not dep_id:
        await state.clear()
        return await message.answer("Envie /start e escolha um departamento primeiro.")
    lista_id = data.get("lista_id")
    lista_tipo = data.get("lista_tipo", "avulsa")

    # salva no carrinho (sempre)
    await database.adicionar_ao_carrinho(message.from_user.id, dep_id, produto, qtd, valor)

    # comportamento diferente para listas fixas: NÃO remover do DB
    if lista_id and lista_tipo != "fixa":
        await database.remover_item_lista(lista_id, produto)

    # remove apenas da sessão (itens_pendentes) para refletir "sair temporariamente"
    itens_pendentes = data.get("itens_pendentes", [])
    if produto in itens_pendentes:
        try:
            itens_pendentes.remove(produto)
        except ValueError:
            pass

    # Monta mensagem principal (sucesso) e também inclui o extrato do CARRINHO (melhora UX)
    try:
        # tenta montar extrato do carrinho atual para exibir ao usuário
        carrinho = await database.pegar_carrinho(message.from_user.id, dep_id)
        extrato_carrinho = montar_extrato_carrinho_local(carrinho)
    except Exception:
        extrato_carrinho = None

    # Mensagem de confirmação específica (mantive lógica existente para listas)
    try:
        if lista_id:
            if lista_tipo == "fixa":
                extrato_texto = montar_extrato_texto(itens_pendentes)
                msg_principal = f"✅ {catalogo.formatar(produto)} adicionado ao carrinho!\n\nExtrato (itens restantes nesta compra):\n\n{extrato_texto}"
            else:
                itens_restantes_db = await database.pegar_itens_da_lista(lista_id)
                extrato_texto = montar_extrato_texto(itens_restantes_db)
                msg_principal = f"✅ {catalogo.formatar(produto)} adicionado ao carrinho!\n\nExtrato atualizado da lista:\n\n{extrato_texto}"
        else:
            # sem lista: mostra extrato do carrinho
            if extrato_carrinho:
                msg_principal = f"✅ {catalogo.formatar(produto)} adicionado ao carrinho!\n\nExtrato do carrinho:\n\n{extrato_carrinho}"
            else:
                msg_principal = f"✅ {catalogo.formatar(produto)} adicionado ao carrinho!"
    except Exception:
        msg_principal = f"✅ {catalogo.formatar(produto)} adicionado ao carrinho!"
        extrato_carrinho = None

    await state.update_data(itens_pendentes=itens_pendentes)

    if itens_pendentes:
        await state.set_state(ListaState.compra_navegando)
        await state.update_data(caminho=[])
        opts = categorias_para_itens(itens_pendentes)
        # envia confirmação e pergunta do próximo item
        await message.answer(msg_principal, reply_markup=ReplyKeyboardRemove())
        await message.answer("Próximo item:", reply_markup=kb_opcoes(opts, True))
    else:
        # todos os itens da sessão foram processados
        if lista_id and lista_tipo == "fixa":
            # mostra opções finais específicas para listas fixas
            kb_final = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="Finalizar compra"), KeyboardButton(text="Finalizar lista")]
                ],
                resize_keyboard=True,
            )
            await state.set_state(ListaState.finalizando_opcao)
            # mantém lista_id/lista_nome no estado
            await message.answer(msg_principal)
            await message.answer("Escolha o que deseja fazer com a lista fixa:", reply_markup=kb_final)
            return
        else:
            # comportamento antigo para listas avulsas / sem lista
            if lista_id:
                itens_restantes_db = await database.pegar_itens_da_lista(lista_id)
                if not itens_restantes_db:
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
            else:
                await message.answer(msg_principal)
                await message.answer("✅ Compra finalizada.")
            return await voltar_para_origem(message, state)


# handler para as duas opções finais quando lista é fixa
@router.message(ListaState.finalizando_opcao)
async def finalizar_opcao(message: types.Message, state: FSMContext):
    text = message.text.strip()
    data = await state.get_data()
    lista_id = data.get("lista_id")
    lista_nome = data.get("lista_nome")

    if text == "Finalizar compra":
        # finaliza a sessão/compra, mantém a lista fixa no DB
        await message.answer("✅ Compra finalizada — a lista fixa foi preservada.", reply_markup=kb_menu())
        await limpar_estado_preservando_departamento(state)
        return

    if text == "Finalizar lista":
        if lista_id:
            try:
                deleted = await database.deletar_lista(lista_id)
            except Exception:
                deleted = False
            if deleted:
                await message.answer(f"✅ Lista *{lista_nome}* finalizada e removida.", parse_mode="Markdown", reply_markup=kb_menu())
            else:
                await message.answer("✅ Compra finalizada. Não foi possível remover a lista automaticamente.", reply_markup=kb_menu())
        else:
            await message.answer("Lista não encontrada para remoção.", reply_markup=kb_menu())

        await limpar_estado_preservando_departamento(state)
        return

    # opção inválida
    return await message.answer("Opção inválida. Escolha 'Finalizar compra' ou 'Finalizar lista'.")