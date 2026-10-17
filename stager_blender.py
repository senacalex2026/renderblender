"""
STAGER BLENDER - projeto de render automatizado (Blender 5.2.x)
=================================================================
Como usar:
  1) Cole no Blender (aba Scripting > Text > New), ajuste NOME_PROJETO e execute.
     Primeira execução: cria as pastas, o project_config.json e o .blend do projeto.
  2) Coloque seus arquivos nas pastas:
        01_Modelos/            .fbx .obj .glb .gltf
        02_Materiais/<Nome>/   texturas (ex.: Aco_BaseColor.png, Aco_Roughness.exr ...)
        03_Iluminacao_HDRI/    .hdr / .exr
  3) Edite o project_config.json (HDRI ativo, rotação, força, preset) e execute de novo.
     Nada de mexer no código ou nos nós do Blender.

Pelo terminal (sem abrir a interface):
  blender -b "projeto.blend" -P stager_blender.py -- render final
  blender -b "projeto.blend" -P stager_blender.py -- zip
  blender -b "projeto.blend" -P stager_blender.py -- zip --sem-renders
"""
import json
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import bpy

# ----------------------------------------------------------------------
# AJUSTE AQUI
# ----------------------------------------------------------------------
DIRETORIO_BASE = Path("C:/")   # raiz: o projeto fica em C:\Renderalexdeign
NOME_PROJETO = "Renderalexdeign"

PASTAS = {
    "modelos": "01_Modelos",
    "materiais": "02_Materiais",
    "hdri": "03_Iluminacao_HDRI",
    "renders": "04_Renders_Finais",
}

CONFIG_PADRAO = {
    "hdri": "",                      # nome do arquivo (ex.: "estudio.hdr"); vazio = primeiro da pasta
    "hdri_rotacao": 0.0,             # graus, eixo Z
    "hdri_forca": 1.0,
    "fundo_transparente": False,     # True = PNG com alpha (bom para produto)
    "preset": "final",               # rascunho | final | alta
    "resolucao": [1920, 1080],
    "limite_textura_viewport": "2048",   # '0' = sem limite. Opções: 512,1024,2048,4096,8192
    "limite_textura_render": "2048",     # RTX 3050 4GB: suba para 4096 só se não estourar VRAM
    "importar_modelos": True,
    "criar_materiais": True,
}

PRESETS = {
    "rascunho": {"samples": 64, "escala": 50, "ruido": 0.05},
    "final": {"samples": 300, "escala": 100, "ruido": 0.01},
    "alta": {"samples": 800, "escala": 100, "ruido": 0.005},
}

EXT_HDRI = {".hdr", ".exr"}
EXT_MODELOS = {".fbx", ".obj", ".glb", ".gltf"}
EXT_TEXTURAS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".exr", ".tga"}

# Último "pedaço" do nome do arquivo -> tipo de mapa (padrão de export do Substance)
MAPAS = {
    "base_color": {"basecolor", "base_color", "albedo", "diffuse", "color"},
    "rugosidade": {"roughness", "rough"},
    "metalico": {"metallic", "metalness", "metal"},
    "normal": {"normal", "normalopengl", "nor"},
    "opacidade": {"opacity", "alpha"},
    "emissao": {"emissive", "emission"},
}


def _set(obj, attr, valor):
    """Define uma propriedade sem quebrar o script se ela mudar de nome entre versões."""
    try:
        setattr(obj, attr, valor)
    except (AttributeError, TypeError, ValueError) as e:
        print(f"⚠️ Ignorado {attr}={valor!r}: {e}")


# ----------------------------------------------------------------------
# 1. PROJETO E PASTAS
# ----------------------------------------------------------------------
def descobrir_pasta_projeto():
    """Se já abriu o .blend do projeto, usa a pasta dele; senão usa DIRETORIO_BASE/NOME_PROJETO."""
    if bpy.data.filepath:
        pasta = Path(bpy.data.filepath).parent
        if (pasta / PASTAS["modelos"]).exists():
            return pasta
    return Path(DIRETORIO_BASE) / NOME_PROJETO


def criar_estrutura(pasta):
    pasta.mkdir(parents=True, exist_ok=True)
    for nome in PASTAS.values():
        (pasta / nome).mkdir(exist_ok=True)

    cfg_path = pasta / "project_config.json"
    if not cfg_path.exists():
        cfg_path.write_text(json.dumps(CONFIG_PADRAO, indent=4, ensure_ascii=False), encoding="utf-8")

    leia = pasta / "LEIA-ME.txt"
    if not leia.exists():
        leia.write_text(
            "01_Modelos: .fbx/.obj/.glb\n"
            "02_Materiais: uma subpasta por material, com texturas Nome_BaseColor.png, "
            "Nome_Roughness.png, Nome_Metallic.png, Nome_Normal.png ...\n"
            "03_Iluminacao_HDRI: arquivos .hdr/.exr\n"
            "04_Renders_Finais: saída dos renders\n"
            "Edite project_config.json e rode stager_blender.py de novo.\n",
            encoding="utf-8",
        )
    return cfg_path


def carregar_config(pasta):
    cfg = dict(CONFIG_PADRAO)
    cfg_path = pasta / "project_config.json"
    try:
        cfg.update(json.loads(cfg_path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as e:
        print(f"⚠️ Não consegui ler o config ({e}); usando padrão.")
    return cfg


# ----------------------------------------------------------------------
# 2. GPU E RENDER
# ----------------------------------------------------------------------
def configurar_gpu():
    """Ativa só a NVIDIA (OptiX/CUDA). Desliga CPU e a Intel UHD para não atrapalhar o render."""
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for tipo in ("OPTIX", "CUDA"):
        try:
            prefs.compute_device_type = tipo
        except TypeError:
            continue
        if hasattr(prefs, "refresh_devices"):
            prefs.refresh_devices()
        else:
            prefs.get_devices()
        usados = 0
        for d in prefs.devices:
            d.use = d.type == tipo
            usados += d.use
        if usados:
            print(f"✔️ GPU ativa via {tipo}: {[d.name for d in prefs.devices if d.use]}")
            return True
    print("⚠️ Nenhuma GPU NVIDIA encontrada; o render usará a CPU.")
    return False


def configurar_render(cena, cfg):
    p = PRESETS.get(cfg["preset"], PRESETS["final"])
    cena.render.engine = "CYCLES"
    c = cena.cycles
    _set(c, "device", "GPU" if configurar_gpu() else "CPU")

    _set(c, "use_preview_denoising", True)
    _set(c, "preview_denoiser", "OPTIX")
    _set(c, "preview_samples", 64)

    _set(c, "use_denoising", True)
    _set(c, "denoiser", "OPENIMAGEDENOISE")
    _set(c, "samples", p["samples"])
    _set(c, "use_adaptive_sampling", True)
    _set(c, "adaptive_threshold", p["ruido"])

    cena.render.use_simplify = True  # necessário para o limite de textura valer
    _set(c, "texture_limit", str(cfg["limite_textura_viewport"]))
    _set(c, "texture_limit_render", str(cfg["limite_textura_render"]))

    cena.render.resolution_x, cena.render.resolution_y = cfg["resolucao"]
    cena.render.resolution_percentage = p["escala"]
    cena.render.film_transparent = bool(cfg["fundo_transparente"])
    cena.render.image_settings.file_format = "PNG"
    cena.render.image_settings.color_mode = "RGBA" if cfg["fundo_transparente"] else "RGB"
    _set(cena.render.image_settings, "color_depth", "16")
    print(f"✔️ Render: preset '{cfg['preset']}' ({p['samples']} samples)")


# ----------------------------------------------------------------------
# 3. HDRI
# ----------------------------------------------------------------------
def listar_hdris(pasta):
    return sorted(f.name for f in (pasta / PASTAS["hdri"]).iterdir() if f.suffix.lower() in EXT_HDRI)


def configurar_mundo(cena, pasta, cfg):
    mundo = cena.world or bpy.data.worlds.new("Stager_World")
    cena.world = mundo
    try:
        if not mundo.use_nodes:   # obsoleto no 5.x (sempre usa nós), por isso protegido
            mundo.use_nodes = True
    except Exception:
        pass

    nos, ligacoes = mundo.node_tree.nodes, mundo.node_tree.links
    nos.clear()
    coord = nos.new("ShaderNodeTexCoord")
    mapa = nos.new("ShaderNodeMapping")
    env = nos.new("ShaderNodeTexEnvironment")
    fundo = nos.new("ShaderNodeBackground")
    saida = nos.new("ShaderNodeOutputWorld")
    for i, n in enumerate((coord, mapa, env, fundo, saida)):
        n.location = (-800 + i * 250, 0)

    ligacoes.new(coord.outputs["Generated"], mapa.inputs["Vector"])
    ligacoes.new(mapa.outputs["Vector"], env.inputs["Vector"])
    ligacoes.new(env.outputs["Color"], fundo.inputs["Color"])
    ligacoes.new(fundo.outputs["Background"], saida.inputs["Surface"])

    import math
    mapa.inputs["Rotation"].default_value[2] = math.radians(cfg["hdri_rotacao"])
    fundo.inputs["Strength"].default_value = cfg["hdri_forca"]

    disponiveis = listar_hdris(pasta)
    escolhido = cfg["hdri"] if cfg["hdri"] in disponiveis else (disponiveis[0] if disponiveis else None)
    if cfg["hdri"] and cfg["hdri"] not in disponiveis:
        print(f"⚠️ HDRI '{cfg['hdri']}' não está na pasta. Disponíveis: {disponiveis}")

    if escolhido:
        caminho = pasta / PASTAS["hdri"] / escolhido
        env.image = bpy.data.images.get(escolhido) or bpy.data.images.load(str(caminho))
        print(f"✔️ HDRI: {escolhido}")
    else:
        fundo.inputs["Color"].default_value = (0.05, 0.05, 0.05, 1)
        print("⚠️ Pasta de HDRI vazia: fundo cinza escuro. Coloque um .hdr/.exr e rode de novo.")


# ----------------------------------------------------------------------
# 4. MODELOS E MATERIAIS
# ----------------------------------------------------------------------
def importar_modelos(cena, pasta):
    ja = set(cena.get("stager_modelos", []))
    for arq in sorted((pasta / PASTAS["modelos"]).iterdir()):
        ext = arq.suffix.lower()
        if ext not in EXT_MODELOS or arq.name in ja:
            continue
        try:
            if ext == ".fbx":
                bpy.ops.import_scene.fbx(filepath=str(arq))
            elif ext == ".obj":
                bpy.ops.wm.obj_import(filepath=str(arq))
            else:
                bpy.ops.import_scene.gltf(filepath=str(arq))
            ja.add(arq.name)
            print(f"✔️ Modelo importado: {arq.name}")
        except Exception as e:
            print(f"❌ Falha ao importar {arq.name}: {e}")
    cena["stager_modelos"] = sorted(ja)


def _agrupar_texturas(pasta_mat):
    """Retorna {nome_material: {tipo_mapa: Path}}. Subpasta = material; senão, prefixo do arquivo."""
    grupos = {}
    for arq in sorted(pasta_mat.rglob("*")):
        if arq.suffix.lower() not in EXT_TEXTURAS:
            continue
        pedacos = re.split(r"[_\-. ]+", arq.stem)
        token = pedacos[-1].lower()
        tipo = next((t for t, nomes in MAPAS.items() if token in nomes), None)
        if not tipo:
            continue
        nome = arq.parent.name if arq.parent != pasta_mat else "_".join(pedacos[:-1]) or arq.stem
        grupos.setdefault(nome, {})[tipo] = arq
    return grupos


def _no_textura(nos, arq, nao_cor, y):
    n = nos.new("ShaderNodeTexImage")
    # Reaproveita a imagem só se for o MESMO arquivo (nomes iguais em pastas diferentes
    # como "BaseColor.png" não podem compartilhar a imagem entre materiais).
    alvo = str(arq.resolve())
    img = next((i for i in bpy.data.images
                if i.filepath and str(Path(bpy.path.abspath(i.filepath)).resolve()) == alvo), None)
    n.image = img or bpy.data.images.load(str(arq))
    if nao_cor:
        n.image.colorspace_settings.name = "Non-Color"
    n.location = (-600, y)
    return n


def criar_materiais(pasta):
    criados = {}
    for nome, mapas in _agrupar_texturas(pasta / PASTAS["materiais"]).items():
        mat = bpy.data.materials.get(nome) or bpy.data.materials.new(nome)
        if not mat.node_tree:  # use_nodes é obsoleto no 5.x
            mat.use_nodes = True
        nos, lig = mat.node_tree.nodes, mat.node_tree.links
        nos.clear()
        bsdf = nos.new("ShaderNodeBsdfPrincipled")
        saida = nos.new("ShaderNodeOutputMaterial")
        bsdf.location, saida.location = (0, 0), (300, 0)
        lig.new(bsdf.outputs["BSDF"], saida.inputs["Surface"])

        y = 300
        for tipo, arq in mapas.items():
            tex = _no_textura(nos, arq, tipo not in ("base_color", "emissao"), y)
            y -= 280
            if tipo == "base_color":
                lig.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
            elif tipo == "rugosidade":
                lig.new(tex.outputs["Color"], bsdf.inputs["Roughness"])
            elif tipo == "metalico":
                lig.new(tex.outputs["Color"], bsdf.inputs["Metallic"])
            elif tipo == "opacidade":
                lig.new(tex.outputs["Color"], bsdf.inputs["Alpha"])
            elif tipo == "emissao":
                lig.new(tex.outputs["Color"], bsdf.inputs["Emission Color"])
                bsdf.inputs["Emission Strength"].default_value = 1.0
            elif tipo == "normal":
                nm = nos.new("ShaderNodeNormalMap")
                nm.location = (-300, tex.location.y)
                lig.new(tex.outputs["Color"], nm.inputs["Color"])
                lig.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
        criados[nome] = mat
        print(f"✔️ Material: {nome} ({', '.join(mapas)})")
    return criados


def atribuir_materiais(cena, materiais):
    """Troca o material do slot quando o nome bate com um da biblioteca (padrão Substance)."""
    if not materiais:
        return
    for obj in cena.objects:
        if obj.type != "MESH":
            continue
        for slot in obj.material_slots:
            base = re.sub(r"\.\d{3}$", "", slot.material.name) if slot.material else ""
            if base in materiais:
                slot.material = materiais[base]
        if not obj.material_slots:
            for nome, mat in materiais.items():
                if nome.lower() in obj.name.lower():
                    obj.data.materials.append(mat)
                    break


# ----------------------------------------------------------------------
# 5. SALVAR, RENDERIZAR, ZIP
# ----------------------------------------------------------------------
def salvar(pasta):
    destino = pasta / f"{pasta.name}.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(destino))
    try:
        bpy.ops.file.make_paths_relative()   # projeto portátil dentro do ZIP
        bpy.ops.wm.save_mainfile()
    except Exception as e:
        print(f"⚠️ Caminhos relativos não aplicados: {e}")
    print(f"✔️ Projeto salvo: {destino}")


def renderizar(pasta, cfg, preset=None):
    if preset:
        cfg = dict(cfg, preset=preset)
        configurar_render(bpy.context.scene, cfg)
    cena = bpy.context.scene
    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
    cena.render.filepath = str(pasta / PASTAS["renders"] / f"{pasta.name}_{cfg['preset']}_{carimbo}")
    bpy.ops.render.render(write_still=True)
    print(f"✔️ Render salvo em {cena.render.filepath}")


def gerar_zip(pasta, incluir_renders=True):
    """Gera <projeto>_<data>.zip ao lado da pasta, mantendo a pasta raiz dentro do ZIP."""
    destino = pasta.parent / f"{pasta.name}_{datetime.now():%Y%m%d_%H%M}.zip"
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        for arq in pasta.rglob("*"):
            if not arq.is_file() or arq.suffix.lower() in {".blend1", ".blend2"}:
                continue
            if not incluir_renders and PASTAS["renders"] in arq.relative_to(pasta).parts:
                continue
            z.write(arq, arq.relative_to(pasta.parent))
    print(f"📦 ZIP gerado: {destino}")
    return destino


# ----------------------------------------------------------------------
# ORQUESTRAÇÃO
# ----------------------------------------------------------------------
def preparar_projeto(salvar_arquivo=True):
    pasta = descobrir_pasta_projeto()
    criar_estrutura(pasta)
    cfg = carregar_config(pasta)
    cena = bpy.context.scene

    configurar_render(cena, cfg)
    configurar_mundo(cena, pasta, cfg)
    if cfg["importar_modelos"]:
        importar_modelos(cena, pasta)
    if cfg["criar_materiais"]:
        atribuir_materiais(cena, criar_materiais(pasta))
    if salvar_arquivo:
        salvar(pasta)
    return pasta, cfg


def _principal():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    acao = args[0] if args else "preparar"
    if acao == "render":
        pasta, cfg = preparar_projeto(salvar_arquivo=False)
        renderizar(pasta, cfg, args[1] if len(args) > 1 else None)
    elif acao == "zip":
        gerar_zip(descobrir_pasta_projeto(), incluir_renders="--sem-renders" not in args)
    else:
        preparar_projeto()


_principal()