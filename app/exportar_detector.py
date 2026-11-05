"""Executado apenas durante o build da imagem (com internet).

1. Baixa os pesos pré-treinados do YOLO e exporta o detector para ONNX.
2. Exporta o extrator de características visuais (MobileNetV3-Large, ImageNet)
   usado no aprendizado por exemplos (correções dos visitantes).
A imagem final não precisa do PyTorch nem de internet."""
import shutil
import sys

import torch
import torchvision
from ultralytics import YOLO

nome = sys.argv[1] if len(sys.argv) > 1 else "yolo11n"
destino = sys.argv[2] if len(sys.argv) > 2 else "/modelos/detector.onnx"
destino_extrator = sys.argv[3] if len(sys.argv) > 3 else "/modelos/extrator.onnx"

modelo = YOLO(f"{nome}.pt")
caminho = modelo.export(format="onnx", imgsz=640, opset=17, simplify=False, dynamic=False)
shutil.copy(caminho, destino)
print("Detector exportado para", destino)

m = torchvision.models.mobilenet_v3_large(weights="IMAGENET1K_V2").eval()
extrator = torch.nn.Sequential(m.features, m.avgpool, torch.nn.Flatten(), m.classifier[0], m.classifier[1]).eval()
exemplo = torch.zeros(2, 3, 224, 224)
torch.onnx.export(extrator, exemplo, destino_extrator, input_names=["imagens"], output_names=["vetores"],
                  dynamic_axes={"imagens": {0: "lote"}, "vetores": {0: "lote"}}, opset_version=17)
print("Extrator exportado para", destino_extrator)
