import pickle
import numpy as np
with open('models/sensor_model.pkl', 'rb') as f:
    model = pickle.load(f)
with open('models/sensor_scaler.pkl', 'rb') as f:
    scaler = pickle.load(f)

print(model.classes_)
delta = np.array([[-0.034, -0.034, -0.034, -0.034]])
delta_scaled = scaler.transform(delta)
print(model.predict_proba(delta_scaled))
