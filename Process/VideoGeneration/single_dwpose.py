import os
import torch
from PIL import Image
from easy_dwpose import DWposeDetector

# Cartella in cui si trova questo script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# File di input e output
INPUT_PATH = os.path.join(BASE_DIR, "ciao2.jpeg")
OUTPUT_PATH = os.path.join(BASE_DIR, "ciaoSkeleton.png")


def main():

    # GPU se disponibile, altrimenti CPU
    device = "cuda:0" if torch.cuda.is_available() else "cpu"

    print("Dispositivo utilizzato:", device)

    # Caricamento DWPose
    detector = DWposeDetector(device=device)

    # Caricamento immagine
    image = Image.open(INPUT_PATH).convert("RGB")

    # Generazione skeleton
    skeleton = detector(
        image,
        output_type="pil",
        include_hands=True,
        include_face=True
    )

    # Salvataggio nella stessa cartella
    skeleton.save(OUTPUT_PATH)

    print("Skeleton salvato in:", OUTPUT_PATH)


if __name__ == "__main__":
    main()