# Pipeline Pro Studio (Substance Stager Master Architecture)

Framework profissional de automação e renderização paramétrica para o **Blender**, focado em emular a qualidade de iluminação, câmeras e materiais de estúdio de forma 100% automatizada e via código (Python / `bpy`).

## 🛠️ Tecnologias e Recursos Utilizados
- **Blender API (`bpy`)**: Manipulação paramétrica completa do ambiente 3D.
- **Python**: Arquitetura lógica do pipeline e persistência de dados via JSON.
- **Cycles Engine**: Configuração otimizada nativamente para hardware moderno (Aceleração por GPU via **NVIDIA RTX 3050 / OptiX**).
- **AI Denoising**: Ativação automática do *OpenImageDenoise* para eliminação rápida de ruídos em qualidade estúdio.

## 📁 Estrutura de Arquivos do Framework
- `pipeline_studio_pro.py`: Core do add-on, gerencia o setup de estúdio, corrigindo distorções de perspectiva (câmera de 2 pontos) e gerando iluminação física real (PBR).
- `stager_blender.py`: Utilitário de execução de render em lote estruturado.
- `project_config.json`: Arquivo paramétrico de configurações globais do pipeline.
- `Renderalexdeign.blend`: Arquivo de cena base pré-configurado.
- `.gitignore`: Configuração para impedir o upload de ambientes virtuais pesados (`.venv`).

## 🚀 Como Executar
O script foi desenvolvido de forma genérica e independente de interface. Ele lê as variáveis de ambiente e diretórios a partir do arquivo `project_config.json`. Para executar o pipeline, execute o Blender via prompt apontando para o script principal ou carregue-o na aba de Scripting do Blender.
