```mermaid
flowchart TB

  start[/start] --> escolherDept[Escolher Departamento]
  escolherDept --> menuPrincipal{Menu Principal}
  menuPrincipal --> compras[Compras]
  menuPrincipal --> cadastros[Cadastros]
  menuPrincipal --> historico[Histórico]
  menuPrincipal --> orcamentos[Orçamentos]
  menuPrincipal --> trocarDept[Trocar Departamento]

  %% Compras
  compras --> comprasMenu[Menu de Compras]
  comprasMenu --> compraAvulsa[Compra Avulsa]
  comprasMenu --> minhasListas[Minhas Listas]
  comprasMenu --> verCarrinho[Ver Carrinho]
  comprasMenu --> voltarCompras[Voltar Compras]

  %% Compra Avulsa
  compraAvulsa --> navegarCatalogo[Navegar catálogo]
  navegarCatalogo --> selecionarProduto[Selecionar produto]
  selecionarProduto --> qtd[Digite quantidade]
  qtd --> valor[Digite valor unitário]
  valor --> adicionarCarrinho[Adicionar ao carrinho]
  adicionarCarrinho --> mostrarExtrato[Mostrar extrato do carrinho]
  mostrarExtrato --> navegarCatalogo

  %% Minhas listas - gerenciamento / iniciar compra
  minhasListas --> escolherLista[Escolher lista]
  escolherLista --> adicionarItensList[Adicionar itens (cadastro)]
  escolherLista --> iniciarCompra[Iniciar compra]
  adicionarItensList --> navegarCatalogoLista[Navegar catálogo e adicionar à lista]
  iniciarCompra --> compraNavegando[Compra navegando - itens pendentes]
  compraNavegando --> compraQtd[Quantidade]
  compraQtd --> compraValor[Valor]
  compraValor --> adicionarCarrinho
  compraValor --> finalOpcao{Lista fixa?}
  finalOpcao -->|Sim| finalizarOpcao[Finalizar compra / finalizar lista]
  finalOpcao -->|Não| voltarOrigem[Voltar ao menu / origem]

  %% Ver Carrinho
  verCarrinho --> carrinhoMenu[Menu do carrinho]
  carrinhoMenu --> removerItem[Remover item]
  carrinhoMenu --> limparCarrinho[Limpar carrinho]
  limparCarrinho --> confirmarLimpar[Confirmar / Cancelar]
  carrinhoMenu --> finalizarCompra[Finalizar compra]
  finalizarCompra --> perguntarMercado[Qual o nome do mercado?]
  perguntarMercado --> confirmarFinalizar[Confirmar / Cancelar]
  confirmarFinalizar --> salvarHistorico[Salvar histórico]

  %% Cadastros / Listas
  cadastros --> listasMenu[Gerenciar listas]
  listasMenu --> novaLista[Nova lista (tipo -> nome)]
  listasMenu --> adicionarItens[Adicionar itens]
  listasMenu --> removerItemLista[Remover item]

  %% Orçamentos
  orcamentos --> orcMenu[Menu de orçamentos]
  orcMenu --> novoOrc[Novo orçamento]
  novoOrc --> tipoLoja[Tipo loja (Física / E-commerce)]
  tipoLoja --> nomeLoja[Nome da loja]
  nomeLoja --> descricao[Descrição / Link]
  descricao --> selecionarLista[Selecionar lista]
  selecionarLista --> selecionarCategoria[Categoria / Subcategoria / Produto]
  selecionarCategoria --> qtdOrc[Quantidade]
  qtdOrc --> valorOrc[Valor unitário]
  valorOrc --> confirmarOrc[Finalizar / Adicionar outro item]
  confirmarOrc --> criarOrcamento[Criar orçamento]

  orcMenu --> editarOrc[Editar orçamento]
  editarOrc --> incluirItem[Incluir item]
  editarOrc --> excluirItem[Excluir item]
  editarOrc --> editarItem[Editar item]

  %% Histórico
  historico --> histMenu[Histórico de compras]
  histMenu --> verDetalhe[Selecionar compra e ver itens/total]

  %% Trocar departamento
  trocarDept --> escolherDept

  %% utilitário
  voltarOrigem --> menuPrincipal
  salvarHistorico --> voltarOrigem