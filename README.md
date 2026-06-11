```mermaid
flowchart TB

  %% Menu Principal
  A["/start"] --> B["Escolher Departamento"]
  B --> C{"Menu Principal"}
  C --> D["Compras"]
  C --> E["Cadastros"]
  C --> F["Histórico"]
  C --> G["Orçamentos"]
  C --> H["Trocar Departamento"]
  H --> B

  %% Fluxo de Compras
  D --> D1["Menu de Compras"]
  D1 --> D2["Compra Avulsa"]
  D1 --> D3["Minhas Listas"]
  D1 --> D4["Ver Carrinho"]
  D1 --> D5["Voltar Compras"]

  D2 --> D2a["Navegar catálogo"]
  D2a --> D2b["Selecionar produto"]
  D2b --> D2c["Digite quantidade"]
  D2c --> D2d["Digite valor unitário"]
  D2d --> D2e["Adicionar ao carrinho"]
  D2e --> D2f["Mostrar extrato do carrinho"]
  D2f --> D2a

  %% Fluxo de Listas
  D3 --> D3a["Escolher lista"]
  D3a --> D3b["Adicionar Itens (cadastro)"]
  D3a --> D3c["Iniciar Compra"]
  D3b --> D3d["Navegar catálogo e adicionar à lista"]
  D3c --> D3e["Compra navegando (itens pendentes)"]
  D3e --> D3f["Quantidade"]
  D3f --> D3g["Valor"]
  D3g --> D2e
  D3g --> D3h{"Lista fixa?"}
  D3h -->|Sim| D3i["Finalizar compra / lista"]
  D3h -->|Não| Z["Voltar ao menu / origem"]

  %% Carrinho
  D4 --> D4a["Menu do Carrinho"]
  D4a --> D4b["Remover Item"]
  D4a --> D4c["Limpar Carrinho"]
  D4c --> D4d["Confirmar / Cancelar"]
  D4a --> D4e["Finalizar Compra"]
  D4e --> D4f["Qual o nome do mercado?"]
  D4f --> D4g["Confirmar / Cancelar"]
  D4g --> D4h["Salvar histórico"]
  D4h --> Z

  %% Cadastros
  E --> E1["Gerenciar Listas"]
  E1 --> E2["Nova Lista (nome/tipo)"]
  E1 --> E3["Adicionar Itens"]
  E1 --> E4["Remover Item"]

  %% Orçamentos
  G --> G1["Menu de Orçamentos"]
  G1 --> G2["Novo orçamento"]
  G2 --> G2a["Tipo loja (Física/E-com)"]
  G2a --> G2b["Nome da loja"]
  G2b --> G2c["Descrição / Link"]
  G2c --> G2d["Selecionar lista"]
  G2d --> G2e["Selecionar Categoria/Produto"]
  G2e --> G2f["Quantidade"]
  G2f --> G2g["Valor unitário"]
  G2g --> G2h["Finalizar / Adicionar outro"]
  G2h --> G2i["Criar orçamento"]

  G1 --> G3["Editar orçamento"]
  G3 --> G3a["Incluir / Excluir / Editar item"]

  %% Histórico e Util
  F --> F1["Histórico de compras"]
  F1 --> F2["Ver detalhes (itens/total)"]

  Z --> C