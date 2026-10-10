# privacylib

Biblioteca core unificada do **PrivacyBOT** — uma fachada única, estável e profissional
que centraliza a infraestrutura compartilhada de um bot de Discord (disnake): dados,
isolamento multi-servidor, erros, apresentação (UI), emojis, utilitários, controle de
acesso, marketplace de extensões e bootstrap.

> ⚠️ **Leia antes de usar — estado atual da biblioteca**
>
> Esta biblioteca foi extraída do PrivacyBOT e, **neste momento, não é um pacote
> autônomo instalável**. Vários módulos ainda dependem de componentes internos do bot
> original (`functions.*`, `connections.*`, `core.*`, `tasks.*`) e leem arquivos locais
> como `config.json` e `database/emojis/emojis.json` no momento do import. Portanto, se
> instalada isoladamente, ela **não funcionará sem esses arquivos/módulos presentes**.
>
> Publicamos o código como **referência e base para colaboração**. Para transformá-la
> em um pacote genérico (`pip install privacylib`) de uso geral, é necessário o
> **desacoplamento** descrito mais abaixo.

## Estrutura

```
privacylib/
├── __init__.py        # Fachada: db, guild, errors, ui, emoji, utils, access, perms, extensions
├── db/                # Camada de dados (mongo, store + cache)
├── guild/             # Isolamento multi-servidor (context, store, keys/KeyFactory)
├── errors/            # Captura e log de erros (handler, capture)
├── ui/                # Apresentação (containers, messages, text)
├── emoji/             # Emojis (runtime + manager)
├── utils/             # Utilitários (+ typing)
├── access/            # Controle de acesso / permissões / planos / servidor
├── extensions/        # Marketplace de extensões
└── bot/               # Bootstrap e ciclo de vida (lifecycle, shim_check)
```

## Ideia de uso (quando desacoplada)

```python
from privacylib import db, emoji, ui, guild, utils, access, perms

produtos = guild.get("loja_products")                 # chave por-servidor automática
container = ui.container(conteudo="Olá", cor_hex="#5c5ef0")
if access.pode_usar(guild_id, user_id, "loja"):
    ...
```

## Princípios de design

- **Fachada única e estável** — importa-se de `privacylib`, não de arquivos internos.
- **Camadas claras** — infraestrutura → apresentação → domínio, sem ciclos de import.
- **Identidade de singletons** — um único cache/estado em memória compartilhado.
- **Paridade de API** — assinaturas públicas preservadas.

## O que falta para virar um pacote de uso geral (contribuições bem-vindas)

1. Remover a leitura de `config.json` / `configs/config_mongo.json` no import; receber
   configuração via parâmetros/variáveis de ambiente.
2. Injetar a conexão MongoDB em vez de depender de `connections/mongo_db.py`.
3. Tornar os caminhos de assets (ex.: `database/emojis/emojis.json`) configuráveis.
4. Remover as dependências residuais de `functions.*`, `core.*`, `tasks.*`.
5. Adicionar testes isolados e publicar no PyPI.

## Licença

MIT — veja [LICENSE](LICENSE).
