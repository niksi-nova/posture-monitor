import time
from pipeline.sensor_reader import create_reader
from pipeline.vision_pipeline import start_pipeline
from pipeline.calibration import run_calibration

def main():
    print("Starting sensor reader...")
    reader = create_reader()
    print("Starting vision pipeline...")
    vp = start_pipeline()
    time.sleep(2)
    print(f"Camera available: {vp.is_camera_available()}")
    
    print("Running calibration...")
    try:
        res = run_calibration(reader, vp, progress_callback=lambda f: print(f"Progress: {f:.2f}"))
        print(f"Calibration successful: {res}")
    except Exception as e:
        print(f"Calibration failed: {e}")

if __name__ == "__main__":
    main()
