"""Executado apenas durante o build da imagem (com internet).

1. Baixa os pesos pré-treinados do YOLO e exporta o detector para ONNX.
   O detector só LOCALIZA objetos (caixas); quem dá o nome é o CLIP.
2. Exporta o codificador de imagens do CLIP (ViT-B/32, LAION-2B) para ONNX.
   Ele transforma cada recorte em um vetor de 512 números.
3. Calcula os vetores de TEXTO de cada objeto da base (vocabulario.json).
   Comparar o vetor da imagem com esses vetores dá o nome do objeto.
A imagem final não precisa do PyTorch nem de internet."""
import json
import shutil
import sys

import numpy as np
import open_clip
import torch
from ultralytics import YOLO

nome = sys.argv[1] if len(sys.argv) > 1 else "yolo11n"
destino = sys.argv[2] if len(sys.argv) > 2 else "/modelos"
vocabulario = sys.argv[3] if len(sys.argv) > 3 else "vocabulario.json"

modelo = YOLO(f"{nome}.pt")
caminho = modelo.export(format="onnx", imgsz=640, opset=17, simplify=False, dynamic=False)
shutil.copy(caminho, f"{destino}/detector.onnx")
print("Detector exportado")

clip, _, _ = open_clip.create_model_and_transforms("ViT-B-32", pretrained="laion2b_s34b_b79k")
clip.eval()
torch.onnx.export(clip.visual, torch.zeros(2, 3, 224, 224), f"{destino}/clip_visual.onnx",
                  input_names=["imagens"], output_names=["vetores"],
                  dynamic_axes={"imagens": {0: "lote"}, "vetores": {0: "lote"}}, opset_version=17)
print("CLIP (imagens) exportado")

# Vários modelos de frase por objeto deixam o reconhecimento mais estável ("prompt ensembling").
FRASES = ["a photo of a {}.", "a close-up photo of a {}.", "a photo of a {} held in a hand.", "a blurry photo of a {}."]
dados = json.load(open(vocabulario, encoding="utf-8"))
tokenizador = open_clip.get_tokenizer("ViT-B-32")
vetores = []
with torch.no_grad():
    for obj in dados["objetos"]:
        textos = [f.format(termo) for termo in obj["ingles"] for f in FRASES]
        v = torch.nn.functional.normalize(clip.encode_text(tokenizador(textos)), dim=1).mean(0)
        vetores.append(torch.nn.functional.normalize(v, dim=0).numpy())
np.save(f"{destino}/clip_texto.npy", np.stack(vetores).astype(np.float32))
shutil.copy(vocabulario, f"{destino}/vocabulario.json")
print(f"Vetores de texto calculados para {len(vetores)} objetos")
