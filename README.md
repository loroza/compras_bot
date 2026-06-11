```mermaid
flowchart TB
  Start([/start]) --> EscolherDepartamento["Escolher Departamento"]
  EscolherDepartamento --> MenuPrincipal{ "Menu Principal" }
  MenuPrincipal --> Compras["Compras"]
  MenuPrincipal --> Cadastros["Cadastros"]
  MenuPrincipal --> Historico["Histórico"]
  MenuPrincipal --> Orcamentos["Orçamentos"]
  MenuPrincipal --> TrocarDept["Trocar Departamento"]

  %% Compras
  Compras --> ComprasMenu["Menu de Compras"]
  ComprasMenu --> CompraAvulsa["Compra Avulsa"]
  ComprasMenu --> MinhasListas["Minhas Listas"]
  ComprasMenu --> VerCarrinho["Ver Carrinho"]
  ComprasMenu --> VoltarCompras["Voltar Compras"]

  %% Compra Avulsa flow
  CompraAvulsa --> NavegarCatalogo["Navegar catálogo"]
  NavegarCatalogo --> SelecionarProduto["Selecionar produto"]
  SelecionarProduto --> Qtd["Digite quantidade"]
  Qtd --> Valor["Digite valor unitário"]
  Valor --> AdicionarCarrinho["adicionar_ao_carrinho()"]
  AdicionarCarrinho --> MostrarExtrato["Mostrar extrato do carrinho"]
  MostrarExtrato --> NavegarCatalogo

  %% Minhas listas -> gerenciamento/iniciar compra
  MinhasListas --> EscolherLista["Escolher lista"]
  EscolherLista --> AdicionarItensList["Adicionar Itens (cadastro)"]
  EscolherLista --> IniciarCompra["Iniciar Compra"]
  AdicionarItensList --> NavegCatalogoList["Navegar catálogo e adicionar à lista"]
  IniciarCompra --> CompraNavegando["compra_navegando (itens_pendentes)"]
  CompraNavegando --> CompraQtd["compra_quantidade"]
  CompraQtd --> CompraValor["compra_valor"]
  CompraValor --> AdicionarCarrinho
  CompraValor --> FinalOpcao{ "Lista fixa?" }
  FinalOpcao -->|Sim| FinalizarOpcao["Finalizar compra / Finalizar lista"]
  FinalOpcao -->|Não| VoltarOrigem["Voltar ao menu / origem"]

  %% Ver Carrinho
  VerCarrinho --> CarrinhoMenu["Menu do Carrinho"]
  CarrinhoMenu --> RemoverItem["Remover Item"]
  CarrinhoMenu --> LimparCarrinho["Limpar Carrinho"]
  LimparCarrinho --> ConfirmarLimpar["Confirmar / Cancelar"]
  CarrinhoMenu --> FinalizarCompra["Finalizar Compra"]
  FinalizarCompra --> PerguntarMercado["Qual o nome do mercado?"]
  PerguntarMercado --> ConfirmarFinalizar["Confirmar / Cancelar"]
  ConfirmarFinalizar --> SalvarHistorico["salvar_historico()"]

  %% Cadastros / Listas
  Cadastros --> ListasMenu["Gerenciar Listas"]
  ListasMenu --> NovaLista["Nova Lista (tipo -> nome)"]
  ListasMenu --> AdicionarItens["Adicionar Itens"]
  ListasMenu --> RemoverItemLista["Remover Item"]

  %% Orçamentos
  Orcamentos --> OrcMenu["Menu de Orçamentos"]
  OrcMenu --> NovoOrc["Novo orçamento"]
  NovoOrc --> TipoLoja["Tipo loja (Física / E-commerce)"]
  TipoLoja --> NomeLoja["Nome da loja"]
  NomeLoja --> Descricao["Descrição / Link"]
  Descricao --> SelecionarLista["Selecionar lista"]
  SelecionarLista --> SelecionarCategoria["Categoria -> Subcategoria -> Produto"]
  SelecionarCategoria --> QtdOrc["Quantidade"]
  QtdOrc --> ValorOrc["Valor unitário"]
  ValorOrc --> ConfirmarOrc["Finalizar / Adicionar outro item"]
  ConfirmarOrc --> CriarOrcamento["criar_orcamento()"]

  OrcMenu --> EditarOrc["Editar orçamento"]
  EditarOrc --> IncluirItem["Incluir item"]
  EditarOrc --> ExcluirItem["Excluir item"]
  EditarOrc --> EditarItem["Editar item"]

  %% Histórico (compras)
  Historico --> HistMenu["Histórico de compras"]
  HistMenu --> VerDetalhe["Selecionar compra e ver itens / total"]

  %% Trocar departamento
  TrocarDept --> EscolherDepartamento

  %% utility
  VoltarOrigem --> MenuPrincipal
  SalvarHistorico --> VoltarOrigem