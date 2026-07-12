import json
import os
import time

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove

import catalogo
import database


print(f"[STARTUP] listas.py carregado | PID={os.getpid()} | ts={time.time():.3f}")

router = Router()


class ListaState(StatesGroup):
    criando_tipo = State()
    criando_nome = State()

    escolhendo_lista = State()
    escolhendo_lista_remover = State()

    navegando_catalogo = State()
    removendo_navegando = State()

    compra_navegando = State()
    compra_quantidade = State()
    compra_valor = State()

    finalizando_opcao = State()


# ============================================================
# LOG / DEBUG
# ============================================================

async def log_handler(handler_name: str, message: types.Message, state: FSMContext):
    """
    Registro simples para identificar qual handler está tratando
    cada mensagem e qual estado estava ativo.
    """
    try:
        state_name = await state.get_state()
        state_data = await state.get_data()
    except Exception as erro:
        state_name = f"ERRO_AO_LER_ESTADO: {erro}"
        state_data = {}

    user_id = getattr(getattr(message, "from_user", None), "id", None)
    texto = getattr(message, "text", None)

    try:
        dados_json = json.dumps(
            state_data,
            default=str,
            ensure_ascii=False,
        )
    except Exception:
        dados_json = str(state_data)

    print(
        f"[HANDLER] "
        f"PID={os.getpid()} "
        f"handler={handler_name} "
        f"ts={time.time():.3f} "
        f"user={user_id} "
        f"text={texto!r} "
        f"state={state_name} "
        f"data={dados_json}"
    )


# ============================================================
# KEYBOARDS
# ============================================================

def kb_menu():
    """
    Menu auxiliar de compras.
    O menu principal oficial continua sendo montado pelo main.py.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🛒 Compra Avulsa"),
                KeyboardButton(text="📋 Minhas Listas"),
            ],
            [
                KeyboardButton(text="📦 Ver Carrinho"),
                KeyboardButton(text="🏁 Finalizar"),
            ],
        ],
        resize_keyboard=True,
    )


def kb_menu_principal():
    """
    Replica o menu principal sem importar main.py,
    evitando dependência circular entre main.py e listas.py.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🛒 Compras"),
                KeyboardButton(text="📲 Cadastros"),
            ],
            [
                KeyboardButton(text="📜 Histórico"),
                KeyboardButton(text="🔄 Trocar Departamento"),
            ],
        ],
        resize_keyboard=True,
    )


def kb_compras():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🛒 Compra Avulsa"),
                KeyboardButton(text="📋 Minhas Listas"),
            ],
            [
                KeyboardButton(text="📦 Ver Carrinho"),
            ],
            [
                KeyboardButton(text="⬅️ Menu Principal"),
            ],
        ],
        resize_keyboard=True,
    )


def kb_listas_menu(allow_iniciar: bool = True):
    """
    Menu de gerenciamento de listas dentro de Cadastros.
    """
    linhas = [
        [KeyboardButton(text="➕ Nova Lista")],
        [KeyboardButton(text="📝 Adicionar Itens")],
    ]

    if allow_iniciar:
        linhas[-1].append(KeyboardButton(text="🚀 Iniciar Compra"))

    linhas.append(
        [
            KeyboardButton(text="🗑️ Remover Item"),
            KeyboardButton(text="⬅️ Menu Principal"),
        ]
    )

    return ReplyKeyboardMarkup(
        keyboard=linhas,
        resize_keyboard=True,
    )


def kb_opcoes(opcoes, voltar: bool = True):
    """
    Cria uma lista vertical de opções do catálogo.
    """
    botoes = []

    for opcao in opcoes:
        botoes.append(
            [KeyboardButton(text=catalogo.formatar(opcao))]
        )

    if voltar:
        botoes.append([KeyboardButton(text="⬅️ Voltar")])

    return ReplyKeyboardMarkup(
        keyboard=botoes,
        resize_keyboard=True,
    )


def kb_lista_escolha(listas):
    """
    Mostra as listas disponíveis para o departamento selecionado.
    """
    botoes = []

    for lista in listas:
        botoes.append(
            [KeyboardButton(text=lista["nome"])]
        )

    botoes.append([KeyboardButton(text="⬅️ Voltar")])

    return ReplyKeyboardMarkup(
        keyboard=botoes,
        resize_keyboard=True,
    )


def kb_tipo_lista():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="Avulsa"),
                KeyboardButton(text="Fixa"),
            ],
            [
                KeyboardButton(text="⬅️ Voltar"),
            ],
        ],
        resize_keyboard=True,
    )


def kb_final_lista_fixa():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="Finalizar compra"),
                KeyboardButton(text="Finalizar lista"),
            ],
        ],
        resize_keyboard=True,
    )


# ============================================================
# HELPERS DE ESTADO
# ============================================================

async def get_dep_from_state(state: FSMContext):
    """
    Retorna:
        departamento_id,
        departamento_nome
    """
    data = await state.get_data()

    return (
        data.get("departamento_id"),
        data.get("departamento_nome"),
    )


async def limpar_estado_preservando_departamento(state: FSMContext):
    """
    Limpa o FSM sem perder o departamento atualmente selecionado.
    """
    data = await state.get_data()

    dados_preservados = {
        chave: data.get(chave)
        for chave in (
            "departamento_id",
            "departamento_nome",
            "departamento_emoji",
            "catalogo_json",
        )
        if data.get(chave) is not None
    }

    await state.clear()

    if dados_preservados:
        await state.set_data(dados_preservados)


def montar_extrato_texto(itens: list) -> str:
    return catalogo.formatar_extrato(itens)


def encontrar_item_raw_por_label(itens: list, label: str):
    """
    Recebe o texto formatado mostrado no botão e retorna o nome raw,
    usado internamente no catálogo e banco.
    """
    for item in itens:
        if catalogo.formatar(item) == label:
            return item

    return None


def montar_extrato_carrinho_local(itens):
    """
    Extrato local para o carrinho, evitando importar funções de main.py.
    """
    if not itens:
        return "Carrinho vazio."

    agrupados = {}
    total = 0.0

    for registro in itens:
        try:
            nome = registro["item_nome"]
            quantidade = float(registro["quantidade"] or 0)
            valor = float(registro["valor_unitario"] or 0)
        except Exception:
            nome = registro[1]
            quantidade = float(registro[2] or 0)
            valor = float(registro[3] or 0)

        if nome not in agrupados:
            agrupados[nome] = {
                "quantidade": quantidade,
                "valor": valor,
            }
        else:
            agrupados[nome]["quantidade"] += quantidade

    linhas = []

    for nome, dados in agrupados.items():
        quantidade = dados["quantidade"]
        valor = dados["valor"]
        subtotal = quantidade * valor
        total += subtotal

        linhas.append(
            f"• {catalogo.formatar(nome)}: "
            f"{quantidade:.3f}x "
            f"R${valor:.2f} "
            f"= R${subtotal:.2f}"
        )

    linhas.append(f"\nValor Total do Carrinho: R${total:.2f}")

    return "\n".join(linhas)


# ============================================================
# HELPERS DE NAVEGAÇÃO DO CATÁLOGO
# ============================================================

def _buscar_produto_recursivo(no, produto):
    """
    Verifica se determinado produto existe dentro de um nó do catálogo,
    inclusive dentro de subcategorias, grupos e estruturas aninhadas.
    """
    if isinstance(no, dict):
        produtos = no.get("produtos")

        if isinstance(produtos, list) and produto in produtos:
            return True

        for chave_container in ("subcategorias", "grupos"):
            subcategorias = no.get(chave_container)

            if isinstance(subcategorias, dict):
                for sub_no in subcategorias.values():
                    if _buscar_produto_recursivo(sub_no, produto):
                        return True

        for chave, valor in no.items():
            if chave in ("produtos", "subcategorias", "grupos"):
                continue

            if isinstance(valor, dict):
                if _buscar_produto_recursivo(valor, produto):
                    return True

            if isinstance(valor, list):
                if produto in valor:
                    return True

                for elemento in valor:
                    if isinstance(elemento, dict):
                        if _buscar_produto_recursivo(elemento, produto):
                            return True

        return False

    if isinstance(no, list):
        return produto in no

    return False


def categorias_para_itens(itens):
    """
    Retorna somente as categorias raiz que contêm algum dos itens informados.
    """
    categorias = []
    categorias_vistas = set()

    for produto in itens:
        for categoria, no_categoria in catalogo.CATALOGO.items():
            if _buscar_produto_recursivo(no_categoria, produto):
                if categoria not in categorias_vistas:
                    categorias.append(categoria)
                    categorias_vistas.add(categoria)

                break

    if not categorias:
        return list(catalogo.CATALOGO.keys())

    return categorias


def _obter_no_por_caminho(caminho):
    """
    Navega diretamente em CATALOGO usando um caminho de chaves.
    Compatível com subcategorias, grupos e chaves diretas.
    """
    if not caminho:
        return None

    no_atual = catalogo.CATALOGO

    for segmento in caminho:
        if not isinstance(no_atual, dict):
            return None

        encontrado = None

        for container in ("subcategorias", "grupos"):
            conteudo = no_atual.get(container)

            if isinstance(conteudo, dict) and segmento in conteudo:
                encontrado = conteudo[segmento]
                break

        if encontrado is None and segmento in no_atual:
            encontrado = no_atual[segmento]

        if encontrado is None:
            return None

        no_atual = encontrado

    return no_atual


def _coletar_todos_produtos():
    """
    Coleta os nomes raw de todos os produtos presentes no catálogo.
    """
    produtos = set()

    def percorrer(no):
        if isinstance(no, dict):
            itens = no.get("produtos")

            if isinstance(itens, list):
                for item in itens:
                    if isinstance(item, str):
                        produtos.add(item)

            for valor in no.values():
                if isinstance(valor, dict):
                    percorrer(valor)

                elif isinstance(valor, list):
                    for elemento in valor:
                        if isinstance(elemento, dict):
                            percorrer(elemento)

        elif isinstance(no, list):
            for elemento in no:
                if isinstance(elemento, dict):
                    percorrer(elemento)

    percorrer(catalogo.CATALOGO)

    return produtos


def opcoes_filtradas_para_itens(caminho, itens):
    """
    Mostra somente categorias, grupos, subcategorias ou produtos que levam
    aos itens efetivamente existentes na lista.

    Isso é usado principalmente no fluxo de:
    - iniciar compra de uma lista;
    - remover item de uma lista.

    No fluxo de adicionar itens, o catálogo completo é mostrado.
    """
    todos_os_produtos = _coletar_todos_produtos()

    mapa_formatado = {
        catalogo.formatar(produto).lower(): produto
        for produto in todos_os_produtos
    }

    itens_raw = set()

    for item in itens:
        if item in todos_os_produtos:
            itens_raw.add(item)
            continue

        texto = str(item).strip()
        texto_lower = texto.lower()

        if texto_lower in mapa_formatado:
            itens_raw.add(mapa_formatado[texto_lower])
            continue

        for label_formatado, raw in mapa_formatado.items():
            if label_formatado == texto_lower:
                itens_raw.add(raw)
                break

    if not caminho:
        categorias = []
        vistas = set()

        for produto in itens_raw:
            for categoria, no_categoria in catalogo.CATALOGO.items():
                if _buscar_produto_recursivo(no_categoria, produto):
                    if categoria not in vistas:
                        categorias.append(categoria)
                        vistas.add(categoria)

                    break

        if not categorias:
            return list(catalogo.CATALOGO.keys())

        return categorias

    no = _obter_no_por_caminho(caminho)

    if no is None:
        return catalogo.obter_opcoes(caminho)

    if not isinstance(no, dict):
        return catalogo.obter_opcoes(caminho)

    opcoes = []
    vistas = set()

    produtos_diretos = no.get("produtos")

    if isinstance(produtos_diretos, list):
        for produto in produtos_diretos:
            if produto in itens_raw and produto not in vistas:
                opcoes.append(produto)
                vistas.add(produto)

    for container in ("subcategorias", "grupos"):
        conteudo = no.get(container)

        if not isinstance(conteudo, dict):
            continue

        for nome_subcategoria, no_subcategoria in conteudo.items():
            contem_item = any(
                _buscar_produto_recursivo(no_subcategoria, produto)
                for produto in itens_raw
            )

            if contem_item and nome_subcategoria not in vistas:
                opcoes.append(nome_subcategoria)
                vistas.add(nome_subcategoria)

    for chave, valor in no.items():
        if chave in ("produtos", "subcategorias", "grupos"):
            continue

        if not isinstance(valor, dict):
            continue

        contem_item = any(
            _buscar_produto_recursivo(valor, produto)
            for produto in itens_raw
        )

        if contem_item and chave not in vistas:
            opcoes.append(chave)
            vistas.add(chave)

    if not opcoes:
        return catalogo.obter_opcoes(caminho)

    return opcoes


# ============================================================
# RETORNOS DE MENU
# ============================================================

async def voltar_para_origem(message: types.Message, state: FSMContext):
    """
    Devolve o usuário para o menu de origem:
    - compras;
    - gerenciamento/cadastros.
    """
    data = await state.get_data()
    origem = data.get("menu_origin", "cadastro")

    if origem == "compras":
        await limpar_estado_preservando_departamento(state)

        return await message.answer(
            "🛒 Menu de Compras:",
            reply_markup=kb_compras(),
        )

    await limpar_estado_preservando_departamento(state)

    return await message.answer(
        "📋 Gerenciar Listas:",
        reply_markup=kb_listas_menu(allow_iniciar=False),
    )


async def iniciar_selecao_lista_para_compra(
    message: types.Message,
    state: FSMContext,
    origem: str = "compras",
):
    """
    Abre a seleção de lista para iniciar uma compra.
    """
    dep_id, _ = await get_dep_from_state(state)

    if not dep_id:
        return await message.answer(
            "Envie /start e escolha um departamento primeiro."
        )

    listas = await database.pegar_listas_disponiveis(dep_id)

    if not listas:
        return await message.answer(
            "Não há listas disponíveis. Crie uma lista primeiro!",
            reply_markup=kb_listas_menu(allow_iniciar=False),
        )

    await state.set_state(ListaState.escolhendo_lista)
    await state.update_data(
        acao="iniciar_compra",
        menu_origin=origem,
    )

    return await message.answer(
        "Selecione a lista para iniciar a compra:",
        reply_markup=kb_lista_escolha(listas),
    )


async def remover_item_start(message: types.Message, state: FSMContext):
    """
    Inicia o fluxo de escolher uma lista para remover itens.
    """
    dep_id, _ = await get_dep_from_state(state)

    if not dep_id:
        return await message.answer(
            "Envie /start e escolha o departamento primeiro."
        )

    listas = await database.pegar_listas_disponiveis(dep_id)

    if not listas:
        return await message.answer(
            "Não há listas disponíveis.",
            reply_markup=kb_listas_menu(allow_iniciar=False),
        )

    await state.set_state(ListaState.escolhendo_lista_remover)
    await state.update_data(
        menu_origin="cadastro",
        acao="remover",
    )

    return await message.answer(
        "Selecione a lista para remover itens:",
        reply_markup=kb_lista_escolha(listas),
    )


# ============================================================
# HANDLERS GERAIS
# ============================================================

@router.message(F.text == "🏁 Finalizar")
async def finalizar_fluxo(message: types.Message, state: FSMContext):
    await limpar_estado_preservando_departamento(state)

    await message.answer(
        "Fluxo finalizado.",
        reply_markup=kb_menu(),
    )


@router.message(F.text == "⬅️ Menu Principal")
async def voltar_menu_principal(message: types.Message, state: FSMContext):
    await limpar_estado_preservando_departamento(state)

    await message.answer(
        "Menu principal:",
        reply_markup=kb_menu_principal(),
    )


# ============================================================
# ENTRADAS PARA LISTAS
# ============================================================

@router.message(F.text == "📋 Minhas Listas")
async def listas_minhas_compras(message: types.Message, state: FSMContext):
    await iniciar_selecao_lista_para_compra(
        message=message,
        state=state,
        origem="compras",
    )


@router.message(F.text == "🚀 Iniciar Compra")
async def iniciar_compra_por_lista(message: types.Message, state: FSMContext):
    await iniciar_selecao_lista_para_compra(
        message=message,
        state=state,
        origem="cadastro",
    )


@router.message(F.text == "📋 Listas")
async def listas_cadastros_manager(message: types.Message, state: FSMContext):
    dep_id, _ = await get_dep_from_state(state)

    if not dep_id:
        return await message.answer(
            "Envie /start e escolha um departamento primeiro."
        )

    await state.set_state(ListaState.escolhendo_lista)
    await state.update_data(
        menu_origin="cadastro",
        acao=None,
    )

    await message.answer(
        "📋 Gerenciar Listas:",
        reply_markup=kb_listas_menu(allow_iniciar=False),
    )


# ============================================================
# CRIAÇÃO DE LISTAS
# ============================================================

@router.message(F.text == "➕ Nova Lista")
async def nova_lista(message: types.Message, state: FSMContext):
    dep_id, _ = await get_dep_from_state(state)

    if not dep_id:
        return await message.answer(
            "Envie /start e escolha o departamento primeiro."
        )

    await state.set_state(ListaState.criando_tipo)

    await message.answer(
        "Qual é o tipo da lista?\n\n"
        "• Avulsa: usada para uma compra e removida ao terminar.\n"
        "• Fixa: reutilizável em várias compras.",
        reply_markup=kb_tipo_lista(),
    )


@router.message(ListaState.criando_tipo)
async def escolher_tipo_lista(message: types.Message, state: FSMContext):
    texto = (message.text or "").strip().lower()

    if message.text == "⬅️ Voltar":
        await state.set_state(ListaState.escolhendo_lista)
        await state.update_data(
            menu_origin="cadastro",
            acao=None,
        )

        return await message.answer(
            "📋 Gerenciar Listas:",
            reply_markup=kb_listas_menu(allow_iniciar=False),
        )

    if texto not in ("avulsa", "fixa"):
        return await message.answer(
            "Escolha uma das opções: Avulsa ou Fixa.",
            reply_markup=kb_tipo_lista(),
        )

    await state.update_data(lista_tipo=texto)
    await state.set_state(ListaState.criando_nome)

    await message.answer(
        "Digite o nome da lista:",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(ListaState.criando_nome)
async def salvar_lista(message: types.Message, state: FSMContext):
    dep_id, _ = await get_dep_from_state(state)

    if not dep_id:
        await limpar_estado_preservando_departamento(state)

        return await message.answer(
            "Envie /start e escolha o departamento primeiro."
        )

    nome_lista = (message.text or "").strip()

    if not nome_lista:
        return await message.answer(
            "O nome da lista não pode ficar vazio. Digite um nome:"
        )

    data = await state.get_data()
    tipo_lista = data.get("lista_tipo", "avulsa")

    sucesso = await database.criar_lista(
        dep_id,
        nome_lista,
        tipo_lista,
    )

    await limpar_estado_preservando_departamento(state)
    await state.set_state(ListaState.escolhendo_lista)
    await state.update_data(
        menu_origin="cadastro",
        acao=None,
    )

    if sucesso:
        return await message.answer(
            f"✅ Lista *{nome_lista}* criada como *{tipo_lista}*.",
            parse_mode="Markdown",
            reply_markup=kb_listas_menu(),
        )

    await message.answer(
        "❌ Não foi possível criar a lista. "
        "Talvez já exista uma lista com esse nome.",
        reply_markup=kb_listas_menu(),
    )


# ============================================================
# ADICIONAR ITENS
# ============================================================

@router.message(F.text == "📝 Adicionar Itens")
async def adicionar_item_start(message: types.Message, state: FSMContext):
    dep_id, _ = await get_dep_from_state(state)

    if not dep_id:
        return await message.answer(
            "Envie /start e escolha um departamento primeiro."
        )

    listas = await database.pegar_listas_disponiveis(dep_id)

    if not listas:
        return await message.answer(
            "Crie uma lista primeiro!",
            reply_markup=kb_listas_menu(),
        )

    await state.set_state(ListaState.escolhendo_lista)
    await state.update_data(
        acao="adicionar",
        menu_origin="cadastro",
    )

    await message.answer(
        "Selecione a lista que receberá os novos itens:",
        reply_markup=kb_lista_escolha(listas),
    )


# ============================================================
# SELEÇÃO DE LISTA: ADICIONAR OU INICIAR COMPRA
# ============================================================

@router.message(ListaState.escolhendo_lista)
async def escolher_lista(message: types.Message, state: FSMContext):
    await log_handler("escolher_lista", message, state)

    texto = message.text or ""

    if texto == "🗑️ Remover Item":
        return await remover_item_start(message, state)

    if texto == "⬅️ Voltar":
        return await voltar_para_origem(message, state)

    data = await state.get_data()
    dep_id, _ = await get_dep_from_state(state)

    if not dep_id:
        await limpar_estado_preservando_departamento(state)

        return await message.answer(
            "Envie /start e escolha um departamento primeiro."
        )

    nome_lista = texto.strip()

    lista = await database.buscar_lista_por_nome(
        dep_id,
        nome_lista,
    )

    if not lista:
        listas_disponiveis = await database.pegar_listas_disponiveis(dep_id)
        nome_normalizado = nome_lista.lower()

        for lista_disponivel in listas_disponiveis:
            if lista_disponivel.get("nome", "").strip().lower() == nome_normalizado:
                lista = lista_disponivel
                break

    if not lista:
        listas = await database.pegar_listas_disponiveis(dep_id)

        if not listas:
            return await message.answer(
                "Lista não encontrada e não há listas disponíveis.",
                reply_markup=kb_listas_menu(allow_iniciar=False),
            )

        await state.set_state(ListaState.escolhendo_lista)

        return await message.answer(
            "Lista não encontrada. Escolha uma das listas abaixo:",
            reply_markup=kb_lista_escolha(listas),
        )

    acao = data.get("acao")

    # --------------------------------------------------------
    # ADICIONAR ITENS
    # --------------------------------------------------------
    if acao == "adicionar":
        itens = await database.pegar_itens_da_lista(lista["id"])
        extrato = montar_extrato_texto(itens)

        await state.set_state(ListaState.navegando_catalogo)
        await state.update_data(
            caminho=[],
            lista_id=lista["id"],
            lista_nome=lista.get("nome"),
            lista_itens=itens,
            acao="adicionar",
            menu_origin="cadastro",
        )

        await message.answer(
            f"Extrato atual da lista *{lista.get('nome')}*:\n\n{extrato}",
            parse_mode="Markdown",
        )

        return await message.answer(
            "Escolha uma categoria:",
            reply_markup=kb_opcoes(catalogo.obter_opcoes([])),
        )

    # --------------------------------------------------------
    # INICIAR COMPRA
    # --------------------------------------------------------
    itens = await database.pegar_itens_da_lista(lista["id"])

    if not itens:
        await database.deletar_lista(lista["id"])

        listas_restantes = await database.pegar_listas_disponiveis(dep_id)

        if not listas_restantes:
            await limpar_estado_preservando_departamento(state)

            return await message.answer(
                "A lista estava vazia e foi excluída automaticamente. "
                "Não há mais listas disponíveis.",
                reply_markup=kb_listas_menu(allow_iniciar=False),
            )

        await state.set_state(ListaState.escolhendo_lista)
        await state.update_data(
            menu_origin="cadastro",
            acao="iniciar_compra",
        )

        return await message.answer(
            "A lista estava vazia e foi excluída automaticamente. "
            "Selecione outra lista:",
            reply_markup=kb_lista_escolha(listas_restantes),
        )

    lista_id = lista["id"]
    lista_tipo = lista.get("tipo", "avulsa")

    await state.set_state(ListaState.compra_navegando)
    await state.update_data(
        itens_pendentes=itens.copy(),
        caminho=[],
        lista_id=lista_id,
        lista_tipo=lista_tipo,
        lista_nome=lista.get("nome"),
        menu_origin=data.get("menu_origin", "compras"),
        acao="iniciar_compra",
    )

    categorias = categorias_para_itens(itens)

    await message.answer(
        f"🛒 Iniciando compra da lista: *{lista.get('nome')}*",
        parse_mode="Markdown",
        reply_markup=kb_opcoes(categorias),
    )


# ============================================================
# NAVEGAÇÃO PARA ADICIONAR ITENS
# ============================================================

@router.message(ListaState.navegando_catalogo)
async def navegar_adicionar_item(message: types.Message, state: FSMContext):
    await log_handler("navegar_adicionar_item", message, state)

    data = await state.get_data()
    caminho = data.get("caminho", [])
    texto = message.text or ""

    if texto == "⬅️ Voltar":
        if not caminho:
            return await voltar_para_origem(message, state)

        caminho.pop()

        await state.update_data(caminho=caminho)

        return await message.answer(
            "Selecione:",
            reply_markup=kb_opcoes(catalogo.obter_opcoes(caminho)),
        )

    tipo, chave = catalogo.identificar_escolha(
        caminho,
        texto.strip(),
    )

    if tipo == "categoria":
        caminho.append(chave)

        await state.update_data(caminho=caminho)

        return await message.answer(
            "Selecione:",
            reply_markup=kb_opcoes(catalogo.obter_opcoes(caminho)),
        )

    if tipo == "produto":
        dep_id, _ = await get_dep_from_state(state)
        nome_lista = data.get("lista_nome")

        if not nome_lista:
            return await message.answer(
                "Lista não encontrada no estado. Reabra o fluxo."
            )

        lista = await database.buscar_lista_por_nome(
            dep_id,
            nome_lista,
        )

        if not lista:
            return await message.answer(
                "Lista não encontrada no banco de dados."
            )

        await database.adicionar_item_lista(
            lista["id"],
            chave,
        )

        itens_atualizados = await database.pegar_itens_da_lista(lista["id"])
        extrato = montar_extrato_texto(itens_atualizados)

        await state.update_data(
            lista_itens=itens_atualizados,
            caminho=caminho,
            lista_nome=nome_lista,
        )

        await message.answer(
            f"✅ {catalogo.formatar(chave)} foi adicionado à lista "
            f"*{nome_lista}*!\n\n"
            f"Extrato atualizado:\n\n{extrato}",
            parse_mode="Markdown",
        )

        return await message.answer(
            "Deseja adicionar mais itens? Selecione:",
            reply_markup=kb_opcoes(catalogo.obter_opcoes(caminho)),
        )

    await message.answer("Escolha inválida. Use os botões exibidos.")


# ============================================================
# REMOVER ITENS
# ============================================================

@router.message(ListaState.escolhendo_lista_remover)
async def escolher_lista_remover(message: types.Message, state: FSMContext):
    await log_handler("escolher_lista_remover", message, state)

    texto = message.text or ""

    if texto == "⬅️ Voltar":
        await state.set_state(ListaState.escolhendo_lista)
        await state.update_data(
            menu_origin="cadastro",
            acao=None,
        )

        return await message.answer(
            "📋 Gerenciar Listas:",
            reply_markup=kb_listas_menu(allow_iniciar=False),
        )

    dep_id, _ = await get_dep_from_state(state)

    if not dep_id:
        await limpar_estado_preservando_departamento(state)

        return await message.answer(
            "Envie /start e escolha um departamento primeiro."
        )

    lista = await database.buscar_lista_por_nome(
        dep_id,
        texto.strip(),
    )

    if not lista:
        listas = await database.pegar_listas_disponiveis(dep_id)

        return await message.answer(
            "Lista não encontrada. Escolha uma lista abaixo:",
            reply_markup=kb_lista_escolha(listas),
        )

    itens = await database.pegar_itens_da_lista(lista["id"])

    if not itens:
        await database.deletar_lista(lista["id"])

        listas = await database.pegar_listas_disponiveis(dep_id)

        if not listas:
            await limpar_estado_preservando_departamento(state)

            return await message.answer(
                "A lista estava vazia e foi excluída automaticamente. "
                "Não há mais listas.",
                reply_markup=kb_listas_menu(allow_iniciar=False),
            )

        return await message.answer(
            "A lista estava vazia e foi excluída automaticamente. "
            "Selecione outra lista:",
            reply_markup=kb_lista_escolha(listas),
        )

    await state.set_state(ListaState.removendo_navegando)
    await state.update_data(
        lista_id=lista["id"],
        lista_nome=lista["nome"],
        lista_itens=itens,
        caminho=[],
        acao="remover_item",
        menu_origin="cadastro",
    )

    categorias = categorias_para_itens(itens)

    await message.answer(
        f"Remover item da lista *{lista['nome']}*.\n\n"
        "Escolha a categoria:",
        parse_mode="Markdown",
        reply_markup=kb_opcoes(categorias),
    )


@router.message(ListaState.removendo_navegando)
async def navegar_remover_item(message: types.Message, state: FSMContext):
    await log_handler("navegar_remover_item", message, state)

    data = await state.get_data()
    caminho = data.get("caminho", [])
    itens_lista = data.get("lista_itens", [])
    texto = message.text or ""

    if texto == "⬅️ Voltar":
        if not caminho:
            dep_id, _ = await get_dep_from_state(state)
            listas = await database.pegar_listas_disponiveis(dep_id)

            await state.set_state(ListaState.escolhendo_lista_remover)

            return await message.answer(
                "Selecione a lista para remover itens:",
                reply_markup=kb_lista_escolha(listas),
            )

        caminho.pop()

        await state.update_data(caminho=caminho)

        opcoes = opcoes_filtradas_para_itens(
            caminho,
            itens_lista,
        )

        return await message.answer(
            "Selecione:",
            reply_markup=kb_opcoes(opcoes),
        )

    tipo, chave = catalogo.identificar_escolha(
        caminho,
        texto.strip(),
    )

    if tipo == "categoria":
        caminho.append(chave)

        await state.update_data(caminho=caminho)

        opcoes = opcoes_filtradas_para_itens(
            caminho,
            itens_lista,
        )

        return await message.answer(
            "Selecione:",
            reply_markup=kb_opcoes(opcoes),
        )

    if tipo == "produto":
        produto = chave
        lista_id = data.get("lista_id")
        nome_lista = data.get("lista_nome")

        if not lista_id:
            return await message.answer(
                "Erro: lista não encontrada no estado."
            )

        await database.remover_item_lista(
            lista_id,
            produto,
        )

        itens_restantes = await database.pegar_itens_da_lista(lista_id)

        if not itens_restantes:
            excluida = await database.deletar_lista(lista_id)

            dep_id, _ = await get_dep_from_state(state)
            listas = await database.pegar_listas_disponiveis(dep_id)

            if excluida and not listas:
                await limpar_estado_preservando_departamento(state)

                return await message.answer(
                    f"✅ {catalogo.formatar(produto)} removido.\n\n"
                    f"A lista *{nome_lista}* ficou vazia e foi excluída.",
                    parse_mode="Markdown",
                    reply_markup=kb_listas_menu(allow_iniciar=False),
                )

            if excluida:
                await state.set_state(ListaState.escolhendo_lista_remover)
                await state.update_data(
                    menu_origin="cadastro",
                    acao="remover",
                )

                return await message.answer(
                    f"✅ {catalogo.formatar(produto)} removido.\n\n"
                    f"A lista *{nome_lista}* ficou vazia e foi excluída. "
                    "Selecione outra lista:",
                    parse_mode="Markdown",
                    reply_markup=kb_lista_escolha(listas),
                )

            await limpar_estado_preservando_departamento(state)

            return await message.answer(
                f"✅ {catalogo.formatar(produto)} removido.\n\n"
                "A lista ficou vazia, mas não foi possível removê-la automaticamente.",
                parse_mode="Markdown",
                reply_markup=kb_listas_menu(allow_iniciar=False),
            )

        await state.update_data(
            lista_itens=itens_restantes,
        )

        opcoes = opcoes_filtradas_para_itens(
            caminho,
            itens_restantes,
        )

        await message.answer(
            f"✅ {catalogo.formatar(produto)} removido da lista "
            f"*{nome_lista}*.",
            parse_mode="Markdown",
        )

        return await message.answer(
            "Selecione o próximo item para remover ou volte:",
            reply_markup=kb_opcoes(opcoes),
        )

    await message.answer("Escolha inválida. Use os botões exibidos.")


# ============================================================
# COMPRA A PARTIR DE LISTA
# ============================================================

@router.message(ListaState.compra_navegando)
async def navegar_compra(message: types.Message, state: FSMContext):
    await log_handler("navegar_compra", message, state)

    data = await state.get_data()
    texto = message.text or ""
    caminho = data.get("caminho", [])
    itens_pendentes = data.get("itens_pendentes", [])

    if texto in ("⬅️ Voltar", "❌ Cancelar"):
        if caminho and texto == "⬅️ Voltar":
            caminho.pop()

            await state.update_data(caminho=caminho)

            opcoes = opcoes_filtradas_para_itens(
                caminho,
                itens_pendentes,
            )

            return await message.answer(
                "Selecione:",
                reply_markup=kb_opcoes(opcoes),
            )

        return await voltar_para_origem(message, state)

    tipo, chave = catalogo.identificar_escolha(
        caminho,
        texto.strip(),
    )

    if tipo == "categoria":
        caminho.append(chave)

        await state.update_data(caminho=caminho)

        opcoes = opcoes_filtradas_para_itens(
            caminho,
            itens_pendentes,
        )

        return await message.answer(
            "Selecione:",
            reply_markup=kb_opcoes(opcoes),
        )

    if tipo == "produto":
        await state.update_data(produto=chave)
        await state.set_state(ListaState.compra_quantidade)

        return await message.answer(
            f"Quanto de *{catalogo.formatar(chave)}*?",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove(),
        )

    await message.answer("Escolha inválida. Use os botões exibidos.")


@router.message(ListaState.compra_quantidade)
async def definir_quantidade_compra(message: types.Message, state: FSMContext):
    texto = (message.text or "").strip()

    try:
        quantidade = float(texto.replace(",", "."))

        if quantidade <= 0:
            raise ValueError

    except (TypeError, ValueError):
        return await message.answer(
            "Digite uma quantidade válida maior que zero.\n"
            "Exemplo: 1, 2.5 ou 0,500"
        )

    await state.update_data(quantidade=quantidade)
    await state.set_state(ListaState.compra_valor)

    await message.answer(
        "Qual é o valor unitário?\n\n"
        "Exemplo: 5,50"
    )


@router.message(ListaState.compra_valor)
async def definir_valor_compra(message: types.Message, state: FSMContext):
    texto = (message.text or "").strip()

    try:
        valor = float(texto.replace(",", "."))

        if valor < 0:
            raise ValueError

    except (TypeError, ValueError):
        return await message.answer(
            "Digite um valor válido.\n"
            "Exemplo: 5,50"
        )

    data = await state.get_data()

    produto = data.get("produto")
    quantidade = data.get("quantidade")
    lista_id = data.get("lista_id")
    lista_tipo = data.get("lista_tipo", "avulsa")
    itens_pendentes = data.get("itens_pendentes", [])

    dep_id, _ = await get_dep_from_state(state)

    if not dep_id:
        await limpar_estado_preservando_departamento(state)

        return await message.answer(
            "Envie /start e escolha um departamento primeiro."
        )

    await database.adicionar_ao_carrinho(
        message.from_user.id,
        dep_id,
        produto,
        quantidade,
        valor,
    )

    # Lista avulsa: compra remove item permanentemente da lista.
    # Lista fixa: item permanece salvo no banco para a próxima compra.
    if lista_id and lista_tipo != "fixa":
        await database.remover_item_lista(
            lista_id,
            produto,
        )

    # Remove o item da sessão atual de compra, inclusive em listas fixas.
    if produto in itens_pendentes:
        try:
            itens_pendentes.remove(produto)
        except ValueError:
            pass

    await state.update_data(
        itens_pendentes=itens_pendentes,
    )

    try:
        carrinho = await database.pegar_carrinho(
            message.from_user.id,
            dep_id,
        )

        extrato_carrinho = montar_extrato_carrinho_local(carrinho)

    except Exception:
        extrato_carrinho = None

    if lista_id and lista_tipo == "fixa":
        extrato_restante = montar_extrato_texto(itens_pendentes)

        mensagem_principal = (
            f"✅ *{catalogo.formatar(produto)}* foi adicionado ao carrinho!\n\n"
            "A lista fixa foi preservada.\n\n"
            "Itens restantes nesta compra:\n\n"
            f"{extrato_restante}"
        )

    elif lista_id:
        itens_banco = await database.pegar_itens_da_lista(lista_id)
        extrato_lista = montar_extrato_texto(itens_banco)

        mensagem_principal = (
            f"✅ *{catalogo.formatar(produto)}* foi adicionado ao carrinho!\n\n"
            "Extrato atualizado da lista:\n\n"
            f"{extrato_lista}"
        )

    elif extrato_carrinho:
        mensagem_principal = (
            f"✅ *{catalogo.formatar(produto)}* foi adicionado ao carrinho!\n\n"
            "Extrato do carrinho:\n\n"
            f"{extrato_carrinho}"
        )

    else:
        mensagem_principal = (
            f"✅ *{catalogo.formatar(produto)}* foi adicionado ao carrinho!"
        )

    if itens_pendentes:
        await state.set_state(ListaState.compra_navegando)
        await state.update_data(caminho=[])

        categorias = categorias_para_itens(itens_pendentes)

        await message.answer(
            mensagem_principal,
            parse_mode="Markdown",
        )

        return await message.answer(
            "Próximo item:",
            reply_markup=kb_opcoes(categorias),
        )

    # --------------------------------------------------------
    # TODOS OS ITENS DA SESSÃO FORAM PROCESSADOS
    # --------------------------------------------------------

    if lista_id and lista_tipo == "fixa":
        await state.set_state(ListaState.finalizando_opcao)

        await message.answer(
            mensagem_principal,
            parse_mode="Markdown",
        )

        return await message.answer(
            "A lista é fixa. O que deseja fazer?",
            reply_markup=kb_final_lista_fixa(),
        )

    if lista_id:
        itens_restantes_banco = await database.pegar_itens_da_lista(lista_id)

        if not itens_restantes_banco:
            excluida = await database.deletar_lista(lista_id)

            if excluida:
                await message.answer(
                    mensagem_principal,
                    parse_mode="Markdown",
                )

                await message.answer(
                    "✅ Todos os itens foram comprados. "
                    "A lista avulsa foi removida automaticamente."
                )

            else:
                await message.answer(
                    mensagem_principal,
                    parse_mode="Markdown",
                )

                await message.answer(
                    "✅ Compra finalizada. "
                    "Não foi possível remover automaticamente a lista avulsa."
                )

        else:
            await message.answer(
                mensagem_principal,
                parse_mode="Markdown",
            )

            await message.answer("✅ Compra finalizada.")

    else:
        await message.answer(
            mensagem_principal,
            parse_mode="Markdown",
        )

        await message.answer("✅ Compra finalizada.")

    await voltar_para_origem(message, state)


# ============================================================
# FINALIZAÇÃO DE LISTA FIXA
# ============================================================

@router.message(ListaState.finalizando_opcao)
async def finalizar_opcao_lista_fixa(message: types.Message, state: FSMContext):
    texto = (message.text or "").strip()
    data = await state.get_data()

    lista_id = data.get("lista_id")
    lista_nome = data.get("lista_nome")

    if texto == "Finalizar compra":
        await limpar_estado_preservando_departamento(state)

        return await message.answer(
            "✅ Compra finalizada. A lista fixa foi preservada para usos futuros.",
            reply_markup=kb_menu(),
        )

    if texto == "Finalizar lista":
        excluida = False

        if lista_id:
            try:
                excluida = await database.deletar_lista(lista_id)
            except Exception:
                excluida = False

        await limpar_estado_preservando_departamento(state)

        if excluida:
            return await message.answer(
                f"✅ A lista fixa *{lista_nome}* foi finalizada e removida.",
                parse_mode="Markdown",
                reply_markup=kb_menu(),
            )

        return await message.answer(
            "✅ Compra finalizada, mas não foi possível remover a lista.",
            reply_markup=kb_menu(),
        )

    await message.answer(
        "Opção inválida. Escolha `Finalizar compra` ou `Finalizar lista`.",
        reply_markup=kb_final_lista_fixa(),
    )