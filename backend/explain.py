import numpy as np
from captum.attr import Saliency
import torch
SENSOR_NAMES = [
    "Cervical",
    "Thoracic",
    "Lumbar",
    "Thoracolumbar Junction"
]
def vision_saliency(model, input_tensor):
    model.eval()

    input_tensor = input_tensor.clone().detach().requires_grad_(True)

    saliency = Saliency(model)

    output = model(input_tensor)
    target = output.argmax(dim=1).item()

    attribution = saliency.attribute(
        input_tensor,
        target=target
    )
    print("ATTR SHAPE:", attribution.shape)
    print("ATTR:", attribution)

    attribution = attribution.abs().mean(dim=-1).squeeze()

    return attribution.tolist()

def generate_explanation(sensor_features, sensor_probs=None, vision_probs=None, vision_model=None, vision_input=None):
    print("=== GENERATING EXPLANATION ===")
    print("vision_model:", vision_model)
    print("vision_input:", vision_input)
    print(sensor_features)

    sensor_features = np.abs(sensor_features)

    idx = int(np.argmax(sensor_features))

    importance = {
        SENSOR_NAMES[i]: float(sensor_features[i])
        for i in range(len(sensor_features))
    }

    return {
        "most_important_sensor": SENSOR_NAMES[idx],
        "sensor_importance": importance,
        "vision": {
            "saliency": vision_saliency(
                vision_model,
                vision_input
            ) if vision_model is not None and vision_input is not None else []
        }
    }
