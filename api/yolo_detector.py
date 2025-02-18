from ultralytics import YOLO
from .models import DetectedObject

model = YOLO("yolov8n.pt")

def detect_objects(image_path):
    results = model(image_path)
    detected_objects = []

    for result in results:
        if hasattr(result, 'boxes'):
            for box in result.boxes:
                obj = DetectedObject.objects.create(
                    label=model.names[int(box.cls[0])],
                    confidence=float(box.conf[0]),
                    x_min=float(box.xyxy[0][0]),
                    y_min=float(box.xyxy[0][1]),
                    x_max=float(box.xyxy[0][2]),
                    y_max=float(box.xyxy[0][3])
                )
                detected_objects.append(obj)
    return detected_objects
