import torch
import numpy as np
model = torch.jit.load('models/vision_lstm.pt')
model.eval()

# Simulate shifted values (this is what is fed into the model)
# Let's say user naturally sits perfectly still at the synthetic baseline
window = np.tile([1.20, 0.02, 1.80, 0.90], (15, 1)).astype(np.float32)
x = torch.tensor(window).unsqueeze(0)

with torch.no_grad():
    logits = model(x)
    probs = torch.softmax(logits, dim=1).numpy()[0]
print("Baseline prediction (Good):", probs)

# Let's say user slouches. user torso_lean increases by 0.3.
window_slouch = np.tile([1.20, 0.02, 2.10, 0.90], (15, 1)).astype(np.float32)
x_slouch = torch.tensor(window_slouch).unsqueeze(0)
with torch.no_grad():
    logits = model(x_slouch)
    probs = torch.softmax(logits, dim=1).numpy()[0]
print("Slouch prediction:", probs)
